"""Execute trades based on portfolio snapshot and LLM decision cache.

Reads the portfolio snapshot (data/signals/portfolio_snapshot.parquet) and the
LLM decision JSON files (data/signals/decisions/{symbol}_{date}.json), then
places spreadbet orders on IG for every instrument where the LLM said GO.

By default the script runs in **dry-run mode** — it prints every action it
would take but does not call place_order. Pass --execute to place real orders.

Staleness guard: if the snapshot's timestamp_of_last_bar is more than 2
calendar days old the script prints an error and exits non-zero.

Usage::

    python scripts/execute_trades.py                   # dry run, all symbols
    python scripts/execute_trades.py --execute         # live — places orders
    python scripts/execute_trades.py --symbol GC=F     # single symbol, dry run
    python scripts/execute_trades.py --symbol GC=F --execute
    python scripts/execute_trades.py --strategy config/strategies/sma_cross.yaml
"""
import argparse
import json
import logging
import sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from trading_lab.audit import AuditAction, log_event
from trading_lab.config.loader import load_instruments
from trading_lab.execution.broker_base import OrderRequest
from trading_lab.execution.ig import IgBrokerAdapter
from trading_lab.llm.context import SignalContext
from trading_lab.llm.decision import DecisionService, PositionManagementDecision
from trading_lab.logging_config import setup_logging
from trading_lab.paths import (
    DECISIONS_DIR,
    INSTRUMENTS_CONFIG,
    SIGNALS_DATA_DIR,
)

setup_logging()
logger = logging.getLogger("execute_trades")

# Snapshot written by run_signals.py
SNAPSHOT_PATH = SIGNALS_DATA_DIR / "portfolio_snapshot.parquet"

# Position-sizing constants
_MIN_SIZE = 0.5
_MAX_SIZE = 50.0          # sensible ceiling — IG rejects huge auto sizes
_RETRY_HALVE_REASONS = {"INSUFFICIENT_FUNDS", "MAX_AUTO_SIZE_EXCEEDED"}

# Maximum age of snapshot before we refuse to trade
_MAX_STALENESS_DAYS = 2

# Audit action for placed orders.  AuditAction does not yet have ORDER_PLACED,
# so we fall back to SIGNAL_GENERATED and emit a warning once.
_ORDER_AUDIT_ACTION: str
try:
    _ORDER_AUDIT_ACTION = AuditAction.ORDER_PLACED  # type: ignore[attr-defined]
except AttributeError:
    logger.warning(
        "AuditAction.ORDER_PLACED is not defined — falling back to "
        "AuditAction.SIGNAL_GENERATED for order audit entries."
    )
    _ORDER_AUDIT_ACTION = AuditAction.SIGNAL_GENERATED


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_snapshot() -> pd.DataFrame:
    """Load the portfolio snapshot parquet. Raises FileNotFoundError if absent."""
    if not SNAPSHOT_PATH.exists():
        raise FileNotFoundError(
            f"Portfolio snapshot not found at {SNAPSHOT_PATH}. "
            "Run scripts/run_signals.py first."
        )
    return pd.read_parquet(SNAPSHOT_PATH)


def _check_staleness(snapshot: pd.DataFrame) -> None:
    """Raise SystemExit if the most recent bar is more than 2 calendar days old.

    We look at the *maximum* timestamp_of_last_bar across all rows so that a
    single stale instrument doesn't block the whole run.
    """
    ts_col = snapshot["timestamp_of_last_bar"].dropna()
    if ts_col.empty:
        logger.error("Snapshot has no valid timestamp_of_last_bar — cannot verify freshness.")
        sys.exit(1)

    # Convert to plain date, handling both tz-aware and naive timestamps.
    def _to_date(ts) -> date:
        if hasattr(ts, "date"):
            return ts.date()
        return pd.Timestamp(ts).date()

    most_recent: date = max(_to_date(ts) for ts in ts_col)
    today = datetime.now(timezone.utc).date()
    age_days = (today - most_recent).days

    if age_days > _MAX_STALENESS_DAYS:
        logger.error(
            "Snapshot is STALE: most recent bar is %s (%d calendar day(s) old). "
            "Refusing to trade. Re-run scripts/run_signals.py to refresh.",
            most_recent,
            age_days,
        )
        sys.exit(1)

    logger.info(
        "Snapshot freshness OK — most recent bar: %s (%d day(s) old).",
        most_recent,
        age_days,
    )


def _build_epic_map(instruments: list[dict]) -> dict[str, str]:
    """Return {symbol: ig_epic} for every instrument that has an ig_epic."""
    return {
        inst["symbol"]: inst.get("ig_epic", "")
        for inst in instruments
    }


def _build_price_factor_map(instruments: list[dict]) -> dict[str, float]:
    """Return {symbol: ig_price_factor} — multiplier from Yahoo price scale to IG points."""
    return {
        inst["symbol"]: float(inst.get("ig_price_factor", 1))
        for inst in instruments
    }


def _build_min_size_map(instruments: list[dict]) -> dict[str, float]:
    """Return {symbol: ig_min_size} — per-instrument minimum deal size from IG."""
    return {
        inst["symbol"]: float(inst.get("ig_min_size", _MIN_SIZE))
        for inst in instruments
    }


def _load_decision(symbol: str, signal_date: date) -> dict | None:
    """Load the LLM decision JSON for symbol+date, or None if not found."""
    filename = f"{symbol}_{signal_date}.json"
    path = DECISIONS_DIR / filename
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read decision file %s: %s", path, exc)
        return None


def _calculate_size(capital: float, stop_distance: float, risk_pct: float = 1.0) -> float:
    """Return £/point size, clamped to [_MIN_SIZE, _MAX_SIZE], rounded to 1 dp."""
    gbp_risk = capital * risk_pct / 100
    if stop_distance <= 0:
        return _MIN_SIZE
    raw = gbp_risk / stop_distance
    return max(_MIN_SIZE, min(_MAX_SIZE, round(raw, 1)))


def _llm_direction_to_ig(direction: str) -> str:
    """Map LLM direction (LONG/SHORT) to IG direction (BUY/SELL)."""
    return "BUY" if direction == "LONG" else "SELL"


def _ig_direction_to_llm(direction: str) -> str:
    """Map IG direction (BUY/SELL) to LLM direction (LONG/SHORT)."""
    return "LONG" if direction == "BUY" else "SHORT"


def _fetch_open_positions_map(
    broker: IgBrokerAdapter | None,
    epic_map: dict[str, str],
) -> dict[str, dict]:
    """Fetch open positions and return a lookup from epic → position dict.

    For dry runs where the broker might not be connected, returns an empty dict.
    """
    if broker is None:
        return {}

    try:
        positions = broker.fetch_positions()
    except Exception as exc:
        logger.warning("Could not fetch open positions: %s — defaulting to empty.", exc)
        return {}

    pos_map: dict[str, dict] = {}
    for pos in positions:
        epic = pos.get("epic", "")
        if epic:
            pos_map[epic] = pos

    logger.info("Fetched %d open position(s).", len(pos_map))
    return pos_map


def _signal_date_for_row(row: pd.Series) -> date | None:
    """Extract the date from timestamp_of_last_bar."""
    ts = row.get("timestamp_of_last_bar")
    if ts is None:
        return None
    try:
        if hasattr(ts, "date"):
            return ts.date()
        return pd.Timestamp(ts).date()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def process_instrument(
    row: pd.Series,
    epic_map: dict[str, str],
    *,
    dry_run: bool,
    broker: IgBrokerAdapter | None,
    capital: float,
    open_positions: dict[str, dict] | None = None,
    price_factor_map: dict[str, float] | None = None,
    min_size_map: dict[str, float] | None = None,
    decision_service: DecisionService | None = None,
) -> dict:
    """Evaluate one snapshot row and optionally place an order.

    Returns a result dict with keys:
        symbol, signal, decision, action, note, deal_ref
    """
    symbol = row["symbol"]
    result = {
        "symbol": symbol,
        "signal": None,
        "direction": None,
        "decision": None,
        "action": "SKIPPED",
        "note": "",
        "deal_ref": "",
    }

    # --- Filter: status ---
    status = str(row.get("status", "")).strip()
    if status != "ok":
        result["note"] = f"status={status!r}"
        logger.info("  SKIPPED %s — %s", symbol, result["note"])
        return result

    # --- Record signal (informational only — no longer gates execution) ---
    raw_signal = row.get("signal")
    if raw_signal is not None and not pd.isna(raw_signal):
        result["signal"] = int(raw_signal)

    # --- Filter: LLM decision ---
    signal_date = _signal_date_for_row(row)
    if signal_date is None:
        result["note"] = "timestamp_of_last_bar missing"
        logger.info("  SKIPPED %s — %s", symbol, result["note"])
        return result

    # --- Position lookup ---
    if open_positions is None:
        open_positions = {}
    epic = epic_map.get(symbol, "")
    existing_pos = open_positions.get(epic) if epic else None

    decision = _load_decision(symbol, signal_date)
    if decision is None:
        if existing_pos:
            # No decision file — leave existing position open (don't close on missing data)
            result["note"] = f"no decision file for {symbol}_{signal_date} — leaving existing position open"
            result["decision"] = "NO FILE"
            result["action"] = "HELD"
            logger.info("  HELD %s — %s", symbol, result["note"])
            return result
        result["note"] = f"no decision file for {symbol}_{signal_date}"
        result["decision"] = "NO FILE"
        logger.info("  SKIPPED %s — %s", symbol, result["note"])
        return result

    llm_rec = decision.get("llm_recommendation", "")
    result["decision"] = llm_rec

    if llm_rec != "GO":
        # LLM says NO_GO or UNCERTAIN — if there's an open position, close it
        if existing_pos:
            pos_deal_id = existing_pos.get("deal_id", "")
            pos_direction = existing_pos.get("direction", "")
            pos_size = existing_pos.get("size", 0)
            if dry_run:
                result["action"] = "DRY RUN: would close"
                result["note"] = (
                    f"llm_recommendation={llm_rec!r} — WOULD CLOSE existing "
                    f"{pos_direction} position (deal_id={pos_deal_id}, size={pos_size})"
                )
                logger.info("  WOULD CLOSE %s — %s %s (LLM=%s)", symbol, pos_direction, pos_size, llm_rec)
            else:
                try:
                    close_ref = broker.close_position(pos_deal_id, pos_direction, pos_size)
                    result["action"] = "CLOSED"
                    result["deal_ref"] = close_ref
                    result["note"] = (
                        f"llm_recommendation={llm_rec!r} — closed {pos_direction} "
                        f"position (deal_id={pos_deal_id}, size={pos_size}, close_ref={close_ref})"
                    )
                    logger.info("  CLOSED %s — %s %s (LLM=%s, close_ref=%s)", symbol, pos_direction, pos_size, llm_rec, close_ref)
                except Exception as exc:
                    result["action"] = "CLOSE_FAILED"
                    result["note"] = f"failed to close position {pos_deal_id}: {exc}"
                    logger.error("  CLOSE FAILED %s — %s", symbol, exc)
            return result

        result["note"] = f"llm_recommendation={llm_rec!r}"
        logger.info("  SKIPPED %s — %s", symbol, result["note"])
        return result

    # --- Direction from LLM ---
    direction = decision.get("direction")
    if direction not in ("LONG", "SHORT"):
        result["note"] = f"invalid direction={direction!r} in LLM decision"
        logger.warning("  SKIPPED %s — %s", symbol, result["note"])
        return result

    result["direction"] = direction
    order_type = decision.get("order_type", "MARKET")
    result["order_type"] = order_type
    side = _llm_direction_to_ig(direction)

    # --- Extract LLM levels early (needed by both position mgmt and new orders) ---
    close = float(row.get("close")) if row.get("close") is not None else None
    llm_stop = decision.get("stop_loss")
    llm_tp = decision.get("take_profit")

    # --- Position management: existing position + GO ---
    if existing_pos:
        pos_direction = existing_pos.get("direction", "")  # BUY or SELL
        pos_deal_id = existing_pos.get("deal_id", "")
        pos_size = existing_pos.get("size", 0)

        if pos_direction == side:
            # Same direction — consult LLM for position management
            if decision_service is not None and not dry_run:
                try:
                    # Get position details
                    pos_open_level = existing_pos.get("open_level", 0)
                    pos_current_level = existing_pos.get("current_level", 0)
                    pos_stop = existing_pos.get("stop_level")
                    pos_limit = existing_pos.get("limit_level")
                    pos_pnl = existing_pos.get("pnl", 0)

                    # Calculate P&L in points
                    if pos_direction == "BUY":
                        pnl_points = pos_current_level - pos_open_level
                    else:
                        pnl_points = pos_open_level - pos_current_level

                    llm_direction = _ig_direction_to_llm(pos_direction)

                    # Build context from snapshot row
                    context = SignalContext(
                        instrument_name=symbol,
                        symbol=symbol,
                        signal_date=signal_date,
                        signal=result["signal"] or 0,
                        signal_direction=llm_direction,
                        close=close or pos_current_level,
                        fast_sma=float(row.get("fast_sma", 0) or 0),
                        slow_sma=float(row.get("slow_sma", 0) or 0),
                        rsi=float(row.get("rsi", 50) or 50),
                        recent_trend_summary=str(row.get("recent_trend_summary", "N/A") or "N/A"),
                        stop_loss_level=float(llm_stop or pos_stop or 0),
                        take_profit_level=float(llm_tp or pos_limit or 0),
                        risk_reward_ratio=float(row.get("risk_reward_ratio", 0) or 0),
                        confidence_score=int(row.get("confidence_score", 0) or 0),
                        conflicting_indicators=bool(row.get("conflicting_indicators", False)),
                        high_volatility=bool(row.get("high_volatility", False)),
                        news_headlines=[],  # News not available at execution time
                        strategy_signals=dict(row.get("strategy_signals", {}) or {}),
                    )

                    # Use current stop/limit, falling back to LLM's original levels
                    current_stop = pos_stop if pos_stop else (float(llm_stop) if llm_stop else 0)
                    current_target = pos_limit if pos_limit else (float(llm_tp) if llm_tp else 0)

                    mgmt = decision_service.manage_position(
                        context=context,
                        position_direction=llm_direction,
                        entry_level=pos_open_level,
                        current_stop=current_stop,
                        current_target=current_target,
                        pnl_points=pnl_points,
                    )

                    if mgmt.recommendation == "CLOSE":
                        # LLM wants to close
                        try:
                            close_ref = broker.close_position(pos_deal_id, pos_direction, pos_size)
                            result["action"] = "CLOSED"
                            result["deal_ref"] = close_ref
                            result["note"] = f"position management: CLOSE — {mgmt.rationale}"
                            logger.info("  CLOSED %s — LLM position management (ref=%s)", symbol, close_ref)
                        except Exception as exc:
                            result["action"] = "CLOSE_FAILED"
                            result["note"] = f"position management CLOSE failed: {exc}"
                            logger.error("  CLOSE FAILED %s — %s", symbol, exc)
                        return result

                    elif mgmt.recommendation == "ADJUST":
                        # Validate stop ratchet: stops can only move in profitable direction
                        new_stop = mgmt.stop_loss
                        new_target = mgmt.take_profit

                        # Apply price factor for IG
                        if price_factor_map is None:
                            price_factor_map = {}
                        ig_factor = price_factor_map.get(symbol, 1.0)

                        # Stop ratchet validation (in Yahoo price space, before IG scaling)
                        if new_stop is not None and current_stop:
                            if llm_direction == "LONG" and new_stop < current_stop:
                                logger.warning("  %s — stop ratchet: rejecting stop %.4f < current %.4f for LONG", symbol, new_stop, current_stop)
                                new_stop = None  # reject — can't widen stop on long
                            elif llm_direction == "SHORT" and new_stop > current_stop:
                                logger.warning("  %s — stop ratchet: rejecting stop %.4f > current %.4f for SHORT", symbol, new_stop, current_stop)
                                new_stop = None  # reject — can't widen stop on short

                        # Convert to IG price scale
                        ig_stop = round(new_stop * ig_factor, 1) if new_stop else None
                        ig_target = round(new_target * ig_factor, 1) if new_target else None

                        if ig_stop is not None or ig_target is not None:
                            try:
                                update_ref = broker.update_position(pos_deal_id, stop_level=ig_stop, limit_level=ig_target)
                                result["action"] = "ADJUSTED"
                                result["deal_ref"] = update_ref
                                changes = []
                                if new_stop:
                                    changes.append(f"stop→{new_stop:.4f}")
                                if new_target:
                                    changes.append(f"target→{new_target:.4f}")
                                result["note"] = f"position management: ADJUST {', '.join(changes)} — {mgmt.rationale}"
                                logger.info("  ADJUSTED %s — %s (ref=%s)", symbol, ', '.join(changes), update_ref)
                            except Exception as exc:
                                result["action"] = "ADJUST_FAILED"
                                result["note"] = f"position management ADJUST failed: {exc}"
                                logger.error("  ADJUST FAILED %s — %s", symbol, exc)
                        else:
                            result["action"] = "HELD"
                            result["note"] = f"ADJUST requested but no valid changes after ratchet — {mgmt.rationale}"
                            logger.info("  HELD %s — adjust had no valid changes", symbol)
                        return result

                    else:  # HOLD
                        result["action"] = "HELD"
                        result["note"] = f"position management: HOLD — {mgmt.rationale}"
                        logger.info("  HELD %s — LLM says hold (deal_id=%s)", symbol, pos_deal_id)
                        return result

                except Exception as exc:
                    # If position management fails, fall back to simple HELD
                    logger.warning("  Position management failed for %s, defaulting to HELD: %s", symbol, exc)
                    result["action"] = "HELD"
                    result["note"] = f"position already open {pos_direction} (mgmt error: {exc})"
                    return result

            # Dry run or no decision service — simple hold
            result["action"] = "HELD" if not dry_run else "DRY RUN: would hold"
            result["note"] = f"position already open in same direction ({pos_direction}, deal_id={pos_deal_id})"
            logger.info("  HELD %s — position already open %s (deal_id=%s)", symbol, pos_direction, pos_deal_id)
            return result

        # Opposite direction — close old position first, then fall through to place new order
        if dry_run:
            logger.info(
                "  WOULD CLOSE %s — flipping direction: old=%s → new=%s (deal_id=%s, size=%s)",
                symbol, pos_direction, side, pos_deal_id, pos_size,
            )
        else:
            try:
                close_ref = broker.close_position(pos_deal_id, pos_direction, pos_size)
                logger.info(
                    "  CLOSED %s — flipped direction: old=%s → new=%s (close_ref=%s)",
                    symbol, pos_direction, side, close_ref,
                )
            except Exception as exc:
                result["action"] = "CLOSE_FAILED"
                result["note"] = f"failed to close opposite position {pos_deal_id} before flip: {exc}"
                logger.error("  CLOSE FAILED %s — could not flip: %s", symbol, exc)
                return result

    # --- Stop distance / limit distance from LLM absolute levels ---
    risk_pct = decision.get("risk_pct", 1.0)
    entry_level = decision.get("entry_level")

    if llm_stop is not None and close is not None and not pd.isna(float(llm_stop)):
        stop_distance = abs(close - float(llm_stop))
    else:
        # Fallback to snapshot's stop_distance for backwards compat
        raw_stop = row.get("stop_distance")
        if raw_stop is not None and not pd.isna(raw_stop) and float(raw_stop) > 0:
            stop_distance = float(raw_stop)
        else:
            result["note"] = "no stop_loss from LLM and no stop_distance in snapshot"
            logger.info("  SKIPPED %s — %s", symbol, result["note"])
            return result

    if stop_distance <= 0:
        result["note"] = f"stop_distance={stop_distance} (not > 0)"
        logger.info("  SKIPPED %s — %s", symbol, result["note"])
        return result

    if llm_tp is not None and close is not None:
        limit_distance = abs(float(llm_tp) - close)
    else:
        # Fallback: 2x stop distance
        limit_distance = stop_distance * 2.0

    # --- Scale distances from Yahoo price units to IG points ---
    if price_factor_map is None:
        price_factor_map = {}
    ig_factor = price_factor_map.get(symbol, 1.0)
    stop_distance = stop_distance * ig_factor
    limit_distance = limit_distance * ig_factor

    # --- Round distances to 1 decimal place (IG rejects excessive precision) ---
    stop_distance = round(stop_distance, 1)
    limit_distance = round(limit_distance, 1)

    # --- Position sizing using LLM risk_pct (in IG point scale) ---
    if min_size_map is None:
        min_size_map = {}
    inst_min_size = min_size_map.get(symbol, _MIN_SIZE)
    size = _calculate_size(capital, stop_distance, risk_pct)
    size = max(size, inst_min_size)

    logger.info(
        "  %s %s — side=%s size=%.1f stop=%.4f target=%.4f risk=%.1f%% entry_ref=%s epic=%s order_type=%s",
        "WOULD PLACE" if dry_run else "PLACING",
        symbol,
        side,
        size,
        stop_distance,
        limit_distance,
        risk_pct,
        entry_level if entry_level is not None else "N/A",
        epic or "(no epic)",
        order_type,
    )

    if dry_run:
        result["action"] = "DRY RUN: would place"
        result["note"] = (
            f"side={side} size={size} stop={llm_stop} target={llm_tp} "
            f"risk={risk_pct}% entry_ref={entry_level} epic={epic or 'MISSING'} "
            f"order_type={order_type}"
        )
        return result

    # --- Place order (live) with retry-on-halve for size rejections ---
    max_attempts = 3
    current_size = size

    # For LIMIT orders, compute the entry level in IG's point scale
    limit_level: float | None = None
    if order_type == "LIMIT" and entry_level is not None:
        limit_level = round(float(entry_level) * ig_factor, 1)

    for attempt in range(1, max_attempts + 1):
        order = OrderRequest(
            symbol=symbol,
            epic=epic,
            side=side,
            size=current_size,
            stop_distance=stop_distance,
            limit_distance=limit_distance,
            order_type=order_type,
            level=limit_level,
        )
        try:
            deal_ref = broker.place_order(order)
            result["action"] = "PLACED"
            result["deal_ref"] = deal_ref
            result["note"] = (
                f"deal_ref={deal_ref} stop={llm_stop} target={llm_tp} "
                f"risk={risk_pct}% size={current_size} entry_ref={entry_level} "
                f"order_type={order_type}"
            )

            log_event(
                _ORDER_AUDIT_ACTION,
                instrument=symbol,
                values={
                    "deal_ref": deal_ref,
                    "side": side,
                    "direction": direction,
                    "size": current_size,
                    "stop_distance": stop_distance,
                    "limit_distance": limit_distance,
                    "stop_loss": llm_stop,
                    "take_profit": llm_tp,
                    "risk_pct": risk_pct,
                    "entry_level": entry_level,
                    "epic": epic,
                    "order_type": order_type,
                    "signal": result["signal"],
                    "signal_date": str(signal_date),
                    "llm_recommendation": llm_rec,
                },
            )
            logger.info("  ORDER PLACED %s — deal_ref=%s (size=%.1f)", symbol, deal_ref, current_size)
            break

        except RuntimeError as exc:
            reason = str(exc)
            # Check if the rejection reason is retryable by halving size
            retryable = any(r in reason for r in _RETRY_HALVE_REASONS)
            if retryable and attempt < max_attempts:
                new_size = round(current_size / 2, 1)
                if new_size < _MIN_SIZE:
                    result["action"] = "FAILED"
                    result["note"] = f"{reason} (halved below min size {_MIN_SIZE})"
                    logger.error("  ORDER FAILED %s — %s (cannot halve further)", symbol, reason)
                    break
                logger.warning(
                    "  ORDER REJECTED %s — %s — halving size %.1f → %.1f (attempt %d/%d)",
                    symbol, reason, current_size, new_size, attempt, max_attempts,
                )
                current_size = new_size
            else:
                result["action"] = "FAILED"
                result["note"] = reason
                logger.error("  ORDER FAILED %s — %s", symbol, reason)
                break

        except Exception as exc:
            result["action"] = "FAILED"
            result["note"] = str(exc)
            logger.error("  ORDER FAILED %s — %s", symbol, exc)
            break

    return result


# ---------------------------------------------------------------------------
# Output table
# ---------------------------------------------------------------------------

def _print_results_table(results: list[dict]) -> None:
    """Print a summary table to stdout with dynamic column widths."""
    # Build row data first so we can measure widths
    rows: list[tuple[str, ...]] = []
    for r in results:
        sig_str = {1: "LONG", -1: "SHORT", 0: "FLAT"}.get(r["signal"], str(r["signal"]))
        rows.append((
            r["symbol"],
            sig_str,
            r.get("direction") or "",
            str(r.get("decision") or ""),
            r["action"],
            r["note"],
        ))

    headers = ("SYMBOL", "SIGNAL", "DIR", "DECISION", "ACTION", "NOTE")
    # Calculate width per column: max of header and all row values
    widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(val))

    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    sep = "-" * (sum(widths) + 2 * (len(widths) - 1))

    print()
    print(sep)
    print(fmt.format(*headers))
    print(sep)
    for row in rows:
        print(fmt.format(*row))
    print(sep)
    print()


# ---------------------------------------------------------------------------
# Positions snapshot persistence (for dashboard)
# ---------------------------------------------------------------------------

def _save_positions_snapshot(
    open_positions: dict[str, dict],
    epic_map: dict[str, str],
    results: list[dict],
) -> None:
    """Persist open positions + execution results as JSON for the dashboard."""
    if not open_positions:
        # No positions — write empty list so dashboard knows it ran
        out_path = SIGNALS_DATA_DIR / "positions_snapshot.json"
        out_path.write_text("[]", encoding="utf-8")
        return

    # Reverse epic_map: epic → symbol
    epic_to_symbol = {v: k for k, v in epic_map.items()}

    # Build results lookup: symbol → result dict
    result_map = {r["symbol"]: r for r in results}

    snapshot = []
    for epic, pos in open_positions.items():
        symbol = epic_to_symbol.get(epic, pos.get("symbol", epic))
        result = result_map.get(symbol, {})
        action = result.get("action", "")
        note = result.get("note", "")

        # Extract position management recommendation from the note
        recommendation = "UNKNOWN"
        rationale = note
        if "HOLD" in action:
            recommendation = "HOLD"
        elif "ADJUSTED" in action:
            recommendation = "ADJUST"
        elif "CLOSED" in action:
            recommendation = "CLOSE"

        snapshot.append({
            "symbol": symbol,
            "ig_epic": epic,
            "direction": pos.get("direction", ""),
            "size": pos.get("size", 0),
            "entry_level": pos.get("open_level", 0),
            "current_level": pos.get("current_level", 0),
            "pnl": pos.get("pnl", 0),
            "stop_level": pos.get("stop_level"),
            "limit_level": pos.get("limit_level"),
            "deal_id": pos.get("deal_id", ""),
            "instrument_name": pos.get("instrument_name", ""),
            "position_decision": {
                "recommendation": recommendation,
                "rationale": rationale,
            },
        })

    out_path = SIGNALS_DATA_DIR / "positions_snapshot.json"
    out_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    logger.info("Positions snapshot saved (%d position(s)) → %s", len(snapshot), out_path)


# ---------------------------------------------------------------------------
# Execution log persistence
# ---------------------------------------------------------------------------

def _save_execution_log(
    results: list[dict],
    capital: float,
    dry_run: bool,
    open_positions: dict[str, dict],
    epic_map: dict[str, str],
    snapshot: pd.DataFrame,
) -> None:
    """Append one row per instrument to the execution log parquet file."""
    log_path = SIGNALS_DATA_DIR / "execution_log.parquet"
    now = datetime.now(timezone.utc)

    # Determine session from current hour
    hour = now.hour
    if hour in (0, 1):
        session = "00:00"
    elif 6 <= hour <= 8:
        session = "07:00"
    elif hour in (13, 14):
        session = "13:30"
    else:
        session = "manual"

    # Reverse epic_map: symbol → epic
    epic_to_symbol = {v: k for k, v in epic_map.items()}

    # Index snapshot by symbol for fast lookup
    snap_by_symbol = snapshot.set_index("symbol") if "symbol" in snapshot.columns else snapshot

    rows = []
    for r in results:
        symbol = r["symbol"]

        # Snapshot data
        snap_row = snap_by_symbol.loc[symbol] if symbol in snap_by_symbol.index else None

        # Position data via epic
        epic = epic_map.get(symbol, "")
        pos = open_positions.get(epic) if epic else None

        # Load decision for extra fields
        signal_date = None
        if snap_row is not None:
            ts = snap_row.get("timestamp_of_last_bar") if hasattr(snap_row, "get") else None
            if ts is not None:
                try:
                    signal_date = ts.date() if hasattr(ts, "date") else pd.Timestamp(ts).date()
                except Exception:
                    pass

        decision = _load_decision(symbol, signal_date) if signal_date else None

        # Direction
        direction = r.get("direction")
        if not direction and decision:
            d = decision.get("direction")
            if d == "LONG":
                direction = "BUY"
            elif d == "SHORT":
                direction = "SELL"
        if not direction and pos:
            direction = pos.get("direction")

        # Size
        size = None
        if decision and decision.get("size"):
            size = decision.get("size")
        if size is None and pos:
            size = pos.get("size")

        # Current price from snapshot
        current_price = None
        if snap_row is not None:
            cp = snap_row.get("close") if hasattr(snap_row, "get") else None
            if cp is not None and not pd.isna(cp):
                current_price = float(cp)

        # Technical signal from snapshot
        technical_signal = None
        if snap_row is not None:
            sig = snap_row.get("signal") if hasattr(snap_row, "get") else None
            if sig is not None and not pd.isna(sig):
                technical_signal = int(sig)

        # Unrealised P&L from position
        unrealised_pnl = None
        if pos:
            unrealised_pnl = pos.get("pnl")

        rows.append({
            "timestamp": now,
            "session": session,
            "symbol": symbol,
            "action": r.get("action", ""),
            "direction": direction,
            "size": size,
            "order_type": decision.get("order_type", "MARKET") if decision else None,
            "entry_level": decision.get("entry_level") if decision else (pos.get("open_level") if pos else None),
            "stop_loss": decision.get("stop_loss") if decision else None,
            "take_profit": decision.get("take_profit") if decision else None,
            "risk_pct": decision.get("risk_pct") if decision else None,
            "current_price": current_price,
            "unrealised_pnl": unrealised_pnl,
            "technical_signal": technical_signal,
            "llm_recommendation": decision.get("llm_recommendation") if decision else None,
            "deal_ref": r.get("deal_ref", ""),
            "rationale": r.get("note", ""),
        })

    new_df = pd.DataFrame(rows)

    # Read existing log and concat
    if log_path.exists():
        try:
            existing = pd.read_parquet(log_path)
            combined = pd.concat([existing, new_df], ignore_index=True)
        except Exception:
            combined = new_df
    else:
        combined = new_df

    combined.to_parquet(log_path, index=False)
    logger.info("Execution log saved (%d new row(s)) → %s", len(new_df), log_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Execute trades from portfolio snapshot + LLM decisions."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Place real orders on IG (default: dry run — prints actions only).",
    )
    parser.add_argument(
        "--symbol",
        default=None,
        help="Process only this symbol (default: all instruments).",
    )
    parser.add_argument(
        "--strategy",
        default=str(ROOT / "config" / "strategies" / "sma_cross.yaml"),
        help=(
            "Path to strategy YAML config — accepted for CLI consistency "
            "with run_signals.py but not used directly here."
        ),
    )
    args = parser.parse_args()

    dry_run = not args.execute

    # Banner — always printed so the operator knows immediately which mode.
    mode_label = "DRY RUN (no orders will be placed)" if dry_run else "*** LIVE — ORDERS WILL BE PLACED ***"
    print()
    print("=" * 70)
    print(f"  execute_trades.py  |  {mode_label}")
    print("=" * 70)
    print()

    # Load snapshot
    try:
        snapshot = _load_snapshot()
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    logger.info("Snapshot loaded — %d instrument(s).", len(snapshot))

    # Staleness guard
    _check_staleness(snapshot)

    # Load instruments config (for epic lookup)
    instruments = load_instruments(INSTRUMENTS_CONFIG)
    epic_map = _build_epic_map(instruments)
    price_factor_map = _build_price_factor_map(instruments)
    min_size_map = _build_min_size_map(instruments)

    # Filter to requested symbol if provided
    if args.symbol:
        snapshot = snapshot[snapshot["symbol"] == args.symbol]
        if snapshot.empty:
            logger.error("Symbol %s not found in snapshot.", args.symbol)
            sys.exit(1)
        logger.info("Filtering to symbol=%s", args.symbol)

    logger.info("Processing %d instrument(s).", len(snapshot))
    logger.info("=" * 60)

    # Initialise broker and fetch account balance.
    # We always connect (even dry run) so we can show the real capital figure.
    broker: IgBrokerAdapter | None = None
    capital: float = 10_000.0  # fallback if broker unavailable
    try:
        broker = IgBrokerAdapter()
        broker._session()  # force early auth check
        capital = broker.fetch_balance()
        logger.info("Account capital: £%.2f", capital)
    except RuntimeError as exc:
        if not dry_run:
            logger.error("Cannot connect to IG: %s", exc)
            sys.exit(1)
        logger.warning("Could not fetch balance (dry run continues with £%.0f): %s", capital, exc)

    # Create decision service for position management
    decision_service: DecisionService | None = None
    try:
        from trading_lab.llm.gemini_client import GeminiClient
        llm_client = GeminiClient()
        decision_service = DecisionService(llm_client)
        logger.info("Decision service initialized for position management")
    except Exception as exc:
        logger.warning("Could not initialize decision service: %s — position management disabled", exc)

    # Fetch open positions for position management
    open_positions = _fetch_open_positions_map(broker, epic_map)

    # NOTE: Instrument processing order could be optimised (e.g. smallest
    # position size first) to maximise the number of trades placed before
    # margin runs out.  For now we process in snapshot order.

    results: list[dict] = []
    for _, row in snapshot.iterrows():
        result = process_instrument(
            row,
            epic_map,
            dry_run=dry_run,
            broker=broker,
            capital=capital,
            open_positions=open_positions,
            price_factor_map=price_factor_map,
            min_size_map=min_size_map,
            decision_service=decision_service,
        )
        results.append(result)

    logger.info("=" * 60)

    # Persist positions snapshot for dashboard (includes LLM management decisions)
    _save_positions_snapshot(open_positions, epic_map, results)

    # Persist execution log
    _save_execution_log(results, capital, dry_run, open_positions, epic_map, snapshot)

    # Print summary table
    _print_results_table(results)

    # Summary counts
    placed = [r for r in results if r["action"] == "PLACED"]
    would_place = [r for r in results if r["action"] == "DRY RUN: would place"]
    would_close = [r for r in results if r["action"] == "DRY RUN: would close"]
    failed = [r for r in results if r["action"] in ("FAILED", "CLOSE_FAILED", "ADJUST_FAILED")]
    skipped = [r for r in results if r["action"] == "SKIPPED"]
    closed = [r for r in results if r["action"] == "CLOSED"]
    held = [r for r in results if r["action"] == "HELD"]
    adjusted = [r for r in results if r["action"] == "ADJUSTED"]

    if dry_run:
        logger.info(
            "Dry-run complete — would place: %d | would close: %d | held: %d | skipped: %d",
            len(would_place),
            len(would_close),
            len(held),
            len(skipped),
        )
    else:
        logger.info(
            "Execution complete — placed: %d | closed: %d | adjusted: %d | held: %d | failed: %d | skipped: %d",
            len(placed),
            len(closed),
            len(adjusted),
            len(held),
            len(failed),
            len(skipped),
        )

    if failed:
        logger.warning("Failed orders: %s", [r["symbol"] for r in failed])
        sys.exit(1)


if __name__ == "__main__":
    main()
