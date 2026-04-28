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
_CAPITAL_GBP = 10_000.0
_MIN_SIZE = 0.5

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


def _calculate_size(stop_distance: float, risk_pct: float = 1.0) -> float:
    """Return £/point size, minimum 0.5, rounded to 1 decimal place."""
    gbp_risk = _CAPITAL_GBP * risk_pct / 100
    if stop_distance <= 0:
        return _MIN_SIZE
    raw = gbp_risk / stop_distance
    return max(_MIN_SIZE, round(raw, 1))


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

    decision = _load_decision(symbol, signal_date)
    if decision is None:
        result["note"] = f"no decision file for {symbol}_{signal_date}"
        result["decision"] = "NO FILE"
        logger.info("  SKIPPED %s — %s", symbol, result["note"])
        return result

    llm_rec = decision.get("llm_recommendation", "")
    result["decision"] = llm_rec

    if llm_rec != "GO":
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
    side = "BUY" if direction == "LONG" else "SELL"

    # --- Stop distance / limit distance from LLM absolute levels ---
    close = float(row.get("close")) if row.get("close") is not None else None

    llm_stop = decision.get("stop_loss")
    llm_tp = decision.get("take_profit")
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

    # --- Position sizing using LLM risk_pct ---
    size = _calculate_size(stop_distance, risk_pct)

    epic = epic_map.get(symbol, "")

    order = OrderRequest(
        symbol=symbol,
        epic=epic,
        side=side,
        size=size,
        stop_distance=stop_distance,
        limit_distance=limit_distance,
    )

    logger.info(
        "  %s %s — side=%s size=%.1f stop=%.4f target=%.4f risk=%.1f%% entry_ref=%s epic=%s",
        "WOULD PLACE" if dry_run else "PLACING",
        symbol,
        side,
        size,
        stop_distance,
        limit_distance,
        risk_pct,
        entry_level if entry_level is not None else "N/A",
        epic or "(no epic)",
    )

    if dry_run:
        result["action"] = "DRY RUN: would place"
        result["note"] = (
            f"side={side} size={size} stop={llm_stop} target={llm_tp} "
            f"risk={risk_pct}% entry_ref={entry_level} epic={epic or 'MISSING'}"
        )
        return result

    # --- Place order (live) ---
    try:
        deal_ref = broker.place_order(order)
        result["action"] = "PLACED"
        result["deal_ref"] = deal_ref
        result["note"] = (
            f"deal_ref={deal_ref} stop={llm_stop} target={llm_tp} "
            f"risk={risk_pct}% entry_ref={entry_level}"
        )

        log_event(
            _ORDER_AUDIT_ACTION,
            instrument=symbol,
            values={
                "deal_ref": deal_ref,
                "side": side,
                "direction": direction,
                "size": size,
                "stop_distance": stop_distance,
                "limit_distance": limit_distance,
                "stop_loss": llm_stop,
                "take_profit": llm_tp,
                "risk_pct": risk_pct,
                "entry_level": entry_level,
                "epic": epic,
                "signal": result["signal"],
                "signal_date": str(signal_date),
                "llm_recommendation": llm_rec,
            },
        )
        logger.info("  ORDER PLACED %s — deal_ref=%s", symbol, deal_ref)

    except Exception as exc:
        result["action"] = "FAILED"
        result["note"] = str(exc)
        logger.error("  ORDER FAILED %s — %s", symbol, exc)

    return result


# ---------------------------------------------------------------------------
# Output table
# ---------------------------------------------------------------------------

def _print_results_table(results: list[dict]) -> None:
    """Print a summary table to stdout."""
    col_widths = {
        "symbol": 10,
        "signal": 7,
        "direction": 9,
        "decision": 12,
        "action": 28,
        "note": 60,
    }

    header = (
        f"{'SYMBOL':<{col_widths['symbol']}}  "
        f"{'SIGNAL':<{col_widths['signal']}}  "
        f"{'DIR':<{col_widths['direction']}}  "
        f"{'DECISION':<{col_widths['decision']}}  "
        f"{'ACTION':<{col_widths['action']}}  "
        f"{'NOTE':<{col_widths['note']}}"
    )
    sep = "-" * len(header)

    print()
    print(sep)
    print(header)
    print(sep)

    for r in results:
        sig_str = {1: "LONG", -1: "SHORT", 0: "FLAT"}.get(r["signal"], str(r["signal"]))
        dir_str = r.get("direction") or ""
        print(
            f"{r['symbol']:<{col_widths['symbol']}}  "
            f"{sig_str:<{col_widths['signal']}}  "
            f"{dir_str:<{col_widths['direction']}}  "
            f"{str(r['decision'] or ''):<{col_widths['decision']}}  "
            f"{r['action']:<{col_widths['action']}}  "
            f"{r['note']:<{col_widths['note']}}"
        )

    print(sep)
    print()


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

    # Filter to requested symbol if provided
    if args.symbol:
        snapshot = snapshot[snapshot["symbol"] == args.symbol]
        if snapshot.empty:
            logger.error("Symbol %s not found in snapshot.", args.symbol)
            sys.exit(1)
        logger.info("Filtering to symbol=%s", args.symbol)

    logger.info("Processing %d instrument(s).", len(snapshot))
    logger.info("=" * 60)

    # Initialise broker only for live runs (avoids unnecessary IG auth in dry run)
    broker: IgBrokerAdapter | None = None
    if not dry_run:
        try:
            broker = IgBrokerAdapter()
            # Force an early auth check so we fail fast before iterating rows.
            broker._session()
        except RuntimeError as exc:
            logger.error("Cannot connect to IG: %s", exc)
            sys.exit(1)

    results: list[dict] = []
    for _, row in snapshot.iterrows():
        result = process_instrument(
            row,
            epic_map,
            dry_run=dry_run,
            broker=broker,
        )
        results.append(result)

    logger.info("=" * 60)

    # Print summary table
    _print_results_table(results)

    # Summary counts
    placed = [r for r in results if r["action"] == "PLACED"]
    would_place = [r for r in results if r["action"] == "DRY RUN: would place"]
    failed = [r for r in results if r["action"] == "FAILED"]
    skipped = [r for r in results if r["action"] == "SKIPPED"]

    if dry_run:
        logger.info(
            "Dry-run complete — would place: %d | skipped: %d",
            len(would_place),
            len(skipped),
        )
    else:
        logger.info(
            "Execution complete — placed: %d | failed: %d | skipped: %d",
            len(placed),
            len(failed),
            len(skipped),
        )

    if failed:
        logger.warning("Failed orders: %s", [r["symbol"] for r in failed])
        sys.exit(1)


if __name__ == "__main__":
    main()
