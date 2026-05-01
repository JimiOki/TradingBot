"""Generate and persist a portfolio signal snapshot for all instruments.

REQ-SIG-007: Every computed Phase 1 signal must be written to a persisted
snapshot on disk before the dashboard reads it.

REQ-WATCH-002: Returns a consolidated signal summary across all instruments
by reading the latest persisted signal snapshot from disk.

Usage::

    python scripts/run_signals.py
    python scripts/run_signals.py --multi
    python scripts/run_signals.py --strategy config/strategies/sma_cross.yaml
    python scripts/run_signals.py --symbol GC=F

Output:
    data/signals/portfolio_snapshot.parquet  — one row per instrument

The snapshot is written atomically (temp file + rename) so the dashboard
never reads a partial file. Exit code is non-zero if any instrument failed.

Multi-strategy mode (--multi or no --strategy specified):
    All YAML files in config/strategies/ are loaded. A consensus vote across
    all strategies determines the primary signal direction. Stop/target levels
    are taken from sma_cross (the primary strategy). Each strategy's last-bar
    signal is passed to the LLM as strategy_signals for weighted decision-making.
"""
import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from trading_lab.audit import AuditAction, log_event
from trading_lab.config.loader import load_instruments
from trading_lab.data.ig_sentiment_fetcher import fetch_ig_sentiment_headline
from trading_lab.data.news_fetcher import fetch_news
from trading_lab.features.indicators import find_swing_levels
from trading_lab.llm.context import build_signal_context
from trading_lab.llm.decision import DecisionService
from trading_lab.llm.explainer import ExplanationService
from trading_lab.llm.factory import create_llm_client
from trading_lab.logging_config import setup_logging
from trading_lab.paths import (
    CURATED_DATA_DIR,
    INSTRUMENTS_CONFIG,
    SIGNAL_NEWS_DIR,
    SIGNALS_DATA_DIR,
    ensure_data_dirs,
)
from trading_lab.strategies.loader import load_strategy

setup_logging()
logger = logging.getLogger("run_signals")

# Stable path the dashboard reads from.
SNAPSHOT_PATH = SIGNALS_DATA_DIR / "portfolio_snapshot.parquet"

# Directory containing strategy YAML configs.
STRATEGIES_CONFIG_DIR = ROOT / "config" / "strategies"

# Name of the primary strategy — used for stop/target levels and as fallback.
PRIMARY_STRATEGY_NAME = "sma_cross"

# Columns carried through from the last signal bar to the snapshot.
# These come from the primary strategy (sma_cross) output — kept unchanged.
_SIGNAL_COLS = [
    "close",
    "signal",
    "fast_sma",
    "slow_sma",
    "rsi",
    "stop_loss_level",
    "take_profit_level",
    "stop_distance",
    "atr_value",
    "confidence_score",
    "signal_strength_pct",
    "conflicting_indicators",
    "high_volatility",
]


def _build_news(symbol: str, instrument: dict, signal_date: str) -> list[dict]:
    """Combine Yahoo Finance headlines with IG client sentiment for LLM context.

    Also persists the headlines (with URLs) to data/signals/news/{symbol}_{date}.json
    so the dashboard can display them as clickable links.
    """
    headlines = fetch_news(symbol)
    ig_sentiment = fetch_ig_sentiment_headline(instrument)
    if ig_sentiment:
        headlines.insert(0, ig_sentiment)  # put sentiment first so LLM sees it early

    # Persist for dashboard (only Yahoo Finance items have URLs worth saving)
    try:
        SIGNAL_NEWS_DIR.mkdir(parents=True, exist_ok=True)
        news_path = SIGNAL_NEWS_DIR / f"{symbol}_{signal_date}.json"
        import json as _json
        news_path.write_text(_json.dumps(headlines, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to persist news for %s: %s", symbol, exc)

    return headlines


def _compute_sr_and_volume(bars: pd.DataFrame, current_close: float) -> dict:
    """Compute support/resistance levels and volume ratio from daily bars.

    Returns a dict with keys: support_levels, resistance_levels, volume_ratio.
    Any value may be None if insufficient data.
    """
    result: dict = {"support_levels": None, "resistance_levels": None, "volume_ratio": None}

    # Use the last 60 bars for swing level detection
    recent = bars.tail(60)
    if len(recent) < 5:
        return result

    highs = recent["High"].tolist() if "High" in recent.columns else []
    lows = recent["Low"].tolist() if "Low" in recent.columns else []

    if highs and lows:
        swing_highs, swing_lows = find_swing_levels(highs, lows, window=2)
        # Filter to nearest 3 above (resistance) and 3 below (support) current close
        resistance = sorted([h for h in swing_highs if h > current_close])[:3]
        support = sorted([s for s in swing_lows if s < current_close], reverse=True)[:3]
        result["resistance_levels"] = resistance if resistance else None
        result["support_levels"] = support if support else None

    # Volume ratio: latest volume / 20-day average
    vol_col = "Volume" if "Volume" in bars.columns else None
    if vol_col and len(bars) >= 20:
        vol_series = bars[vol_col].tail(20)
        avg_vol = vol_series.mean()
        latest_vol = bars[vol_col].iloc[-1]
        if avg_vol and avg_vol > 0:
            result["volume_ratio"] = round(float(latest_vol / avg_vol), 2)

    return result


def curated_path_for(symbol: str, timeframe: str, source: str) -> Path:
    """Return the curated Parquet path for an instrument.

    Matches the naming convention in yfinance_ingest.build_output_paths.
    """
    filename = f"{symbol.lower()}_{timeframe}_{source}.parquet"
    return CURATED_DATA_DIR / filename


def _load_bars(instrument: dict) -> pd.DataFrame | None:
    """Load curated bars for an instrument. Returns None if file is missing."""
    symbol = instrument["symbol"]
    timeframe = instrument.get("timeframe", "1d")
    source = instrument.get("source", "yfinance")
    curated = curated_path_for(symbol, timeframe, source)

    if not curated.exists():
        logger.warning("  ✗ %s — curated file not found: %s", symbol, curated)
        return None

    bars = pd.read_parquet(curated)
    if "timestamp" in bars.columns:
        bars = bars.set_index("timestamp")
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    return bars


def _compute_consensus_signal(strategy_signals: dict) -> int:
    """Compute a consensus primary signal from a dict of strategy signals.

    Rules:
      - Count LONG (1) and SHORT (-1) signals across all strategies.
      - If a strict majority (>50%) agree on direction → use that direction.
      - If tied or no majority → return 0 (flat/neutral).

    Args:
        strategy_signals: Dict mapping strategy name to signal int (-1, 0, 1).

    Returns:
        1, -1, or 0.
    """
    total = len(strategy_signals)
    if total == 0:
        return 0

    longs = sum(1 for v in strategy_signals.values() if v is not None and int(v) == 1)
    shorts = sum(1 for v in strategy_signals.values() if v is not None and int(v) == -1)

    if longs > total / 2:
        return 1
    if shorts > total / 2:
        return -1
    return 0


def _load_all_strategies(strategies_dir: Path) -> dict:
    """Load all strategy YAML files from the given directory.

    Returns a dict mapping YAML filename stem (e.g. "sma_cross") to a
    loaded Strategy instance. Strategies that fail to load are skipped
    with a warning.
    """
    strategies = {}
    yaml_files = sorted(strategies_dir.glob("*.yaml"))
    if not yaml_files:
        logger.warning("No strategy YAML files found in %s", strategies_dir)
        return strategies

    for yaml_path in yaml_files:
        key = yaml_path.stem  # filename without extension
        try:
            strategy = load_strategy(yaml_path)
            strategies[key] = strategy
            logger.info("  Loaded strategy: %s (%s)", key, yaml_path.name)
        except Exception as exc:
            logger.warning("  Skipping strategy %s — load failed: %s", key, exc)

    return strategies


def process_instrument_multi(
    instrument: dict,
    strategies: dict,
    primary_strategy_name: str,
    explanation_svc: ExplanationService,
    decision_svc: DecisionService,
) -> dict:
    """Run ALL strategies on one instrument and return its snapshot row.

    The primary signal is determined by consensus vote across all strategies.
    Stop/target levels are taken from the primary strategy's output (sma_cross).
    All strategy last-bar signals are passed to the LLM as strategy_signals.

    Returns a dict with all snapshot columns populated. If curated data is
    absent or the primary strategy raises, status is set appropriately and signal
    columns are None so the dashboard can display gracefully.
    """
    symbol = instrument["symbol"]
    name = instrument.get("name", symbol)

    bars = _load_bars(instrument)
    if bars is None:
        return {
            "symbol": symbol,
            "name": name,
            "timestamp_of_last_bar": None,
            "status": "data_missing",
            **{col: None for col in _SIGNAL_COLS},
        }

    # Run every strategy and collect the last-bar signal value.
    strategy_signals: dict[str, int] = {}
    primary_last = None
    primary_signals_df = None

    for strat_key, strategy in strategies.items():
        try:
            sig_df = strategy.generate_signals(bars)
            last_val = sig_df.iloc[-1].get("signal") if "signal" in sig_df.columns else None
            strategy_signals[strat_key] = int(last_val) if last_val is not None and pd.notna(last_val) else 0
            if strat_key == primary_strategy_name:
                primary_last = sig_df.iloc[-1]
                primary_signals_df = sig_df
        except Exception as exc:
            logger.warning("  Strategy %s failed for %s: %s", strat_key, symbol, exc)
            strategy_signals[strat_key] = 0

    # If the primary strategy didn't produce output, we can't populate signal cols.
    if primary_last is None:
        logger.error("  ✗ %s — primary strategy (%s) produced no output", symbol, primary_strategy_name)
        return {
            "symbol": symbol,
            "name": name,
            "timestamp_of_last_bar": None,
            "status": f"error: primary strategy {primary_strategy_name} failed",
            **{col: None for col in _SIGNAL_COLS},
        }

    # Compute consensus signal.
    consensus_signal = _compute_consensus_signal(strategy_signals)

    # Build the snapshot row using primary strategy's output columns,
    # but override 'signal' with the consensus value.
    row = {
        "symbol": symbol,
        "name": name,
        "timestamp_of_last_bar": primary_signals_df.index[-1],
        "status": "ok",
    }
    for col in _SIGNAL_COLS:
        if col == "signal":
            row[col] = consensus_signal
        else:
            row[col] = primary_last.get(col) if col in primary_last.index else None

    # Audit entry for the generated signal (REQ-OPS-001)
    log_event(
        AuditAction.SIGNAL_GENERATED,
        instrument=symbol,
        values={
            "signal": int(row["signal"]) if row["signal"] is not None else None,
            "close": float(row["close"]) if row["close"] is not None else None,
            "confidence_score": row["confidence_score"],
            "timestamp_of_last_bar": str(row["timestamp_of_last_bar"]),
        },
    )

    direction = {1: "LONG", -1: "SHORT", 0: "FLAT"}.get(consensus_signal, "FLAT")
    logger.info(
        "  ✓ %s — %s (consensus %d/%d) | close=%.4f | conf=%s | SL=%.4f | TP=%.4f",
        symbol,
        direction,
        max(
            sum(1 for v in strategy_signals.values() if v == 1),
            sum(1 for v in strategy_signals.values() if v == -1),
        ),
        len(strategy_signals),
        primary_last["close"] if "close" in primary_last.index else float("nan"),
        row["confidence_score"],
        primary_last["stop_loss_level"] if "stop_loss_level" in primary_last.index and pd.notna(primary_last["stop_loss_level"]) else float("nan"),
        primary_last["take_profit_level"] if "take_profit_level" in primary_last.index and pd.notna(primary_last["take_profit_level"]) else float("nan"),
    )

    # LLM explanation and decision — always run so users see analysis even on flat signals.
    # Services cache by (symbol, date) so this only hits the API once per day per instrument.
    try:
        from datetime import date
        signal_row_for_llm = {
            **row,
            "signal_date": primary_signals_df.index[-1].date() if hasattr(primary_signals_df.index[-1], "date") else date.today(),
        }
        sr_vol = _compute_sr_and_volume(bars, float(row["close"])) if row["close"] is not None else {}
        ctx = build_signal_context(
            signal_row=signal_row_for_llm,
            instrument=instrument,
            news=_build_news(symbol, instrument, str(primary_signals_df.index[-1].date())),
            strategy_signals=strategy_signals,
            support_levels=sr_vol.get("support_levels"),
            resistance_levels=sr_vol.get("resistance_levels"),
            volume_ratio=sr_vol.get("volume_ratio"),
        )
        explanation_svc.get_or_generate(ctx)
        decision_svc.get_or_generate(ctx)
    except Exception as exc:
        logger.warning("LLM services failed for %s: %s", symbol, exc)

    return row


def process_instrument(instrument: dict, strategy, explanation_svc: ExplanationService, decision_svc: DecisionService) -> dict:
    """Run the strategy on one instrument and return its snapshot row.

    Returns a dict with all snapshot columns populated. If curated data is
    absent or the strategy raises, status is set appropriately and signal
    columns are None so the dashboard can display gracefully.
    """
    symbol = instrument["symbol"]
    name = instrument.get("name", symbol)
    timeframe = instrument.get("timeframe", "1d")
    source = instrument.get("source", "yfinance")

    curated = curated_path_for(symbol, timeframe, source)

    # --- Missing data case (REQ-WATCH-002) ---
    if not curated.exists():
        logger.warning("  ✗ %s — curated file not found: %s", symbol, curated)
        return {
            "symbol": symbol,
            "name": name,
            "timestamp_of_last_bar": None,
            "status": "data_missing",
            **{col: None for col in _SIGNAL_COLS},
        }

    try:
        bars = pd.read_parquet(curated)

        # Restore DatetimeIndex (curated files are stored without index by ingest script)
        if "timestamp" in bars.columns:
            bars = bars.set_index("timestamp")
        if bars.index.tz is None:
            bars.index = bars.index.tz_localize("UTC")

        signals = strategy.generate_signals(bars)
        last = signals.iloc[-1]

        row = {
            "symbol": symbol,
            "name": name,
            "timestamp_of_last_bar": signals.index[-1],
            "status": "ok",
        }
        for col in _SIGNAL_COLS:
            row[col] = last.get(col) if col in last.index else None

        # Audit entry for the generated signal (REQ-OPS-001)
        log_event(
            AuditAction.SIGNAL_GENERATED,
            instrument=symbol,
            values={
                "signal": int(row["signal"]) if row["signal"] is not None else None,
                "close": float(row["close"]) if row["close"] is not None else None,
                "confidence_score": row["confidence_score"],
                "timestamp_of_last_bar": str(row["timestamp_of_last_bar"]),
            },
        )

        direction = {1: "LONG", -1: "SHORT", 0: "FLAT"}.get(
            int(last["signal"]) if pd.notna(last["signal"]) else 0, "FLAT"
        )
        logger.info(
            "  ✓ %s — %s | close=%.4f | conf=%s | SL=%.4f | TP=%.4f",
            symbol,
            direction,
            last["close"],
            row["confidence_score"],
            last["stop_loss_level"] if pd.notna(last["stop_loss_level"]) else float("nan"),
            last["take_profit_level"] if pd.notna(last["take_profit_level"]) else float("nan"),
        )

        # LLM explanation and decision for non-flat signals
        signal_val = int(last["signal"]) if pd.notna(last["signal"]) else 0
        if signal_val != 0:
            try:
                from datetime import date
                signal_row_for_llm = {
                    **row,
                    "signal_date": signals.index[-1].date() if hasattr(signals.index[-1], "date") else date.today(),
                }
                sr_vol = _compute_sr_and_volume(bars, float(last["close"]))
                ctx = build_signal_context(
                    signal_row=signal_row_for_llm,
                    instrument=instrument,
                    news=_build_news(symbol, instrument, str(signals.index[-1].date())),  # REQ-LLM-008
                    support_levels=sr_vol.get("support_levels"),
                    resistance_levels=sr_vol.get("resistance_levels"),
                    volume_ratio=sr_vol.get("volume_ratio"),
                )
                explanation_svc.get_or_generate(ctx)
                decision_svc.get_or_generate(ctx)
            except Exception as exc:
                logger.warning("LLM services failed for %s: %s", symbol, exc)

        return row

    except Exception as exc:
        logger.error("  ✗ %s — strategy error: %s", symbol, exc)
        return {
            "symbol": symbol,
            "name": name,
            "timestamp_of_last_bar": None,
            "status": f"error: {exc}",
            **{col: None for col in _SIGNAL_COLS},
        }


def write_snapshot_atomic(df: pd.DataFrame) -> None:
    """Write snapshot atomically: temp file → rename.

    REQ-SIG-007: A refresh run overwrites the previous snapshot only after
    the new signals have been computed successfully.
    """
    tmp = SNAPSHOT_PATH.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(SNAPSHOT_PATH)
    logger.info("Snapshot written → %s (%d rows)", SNAPSHOT_PATH, len(df))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate portfolio signal snapshot.")
    parser.add_argument(
        "--strategy",
        default=None,
        help="Path to strategy YAML config. When specified, runs single-strategy mode. "
             "Defaults to None (multi-strategy mode).",
    )
    parser.add_argument(
        "--multi",
        action="store_true",
        default=False,
        help="Run all strategies from config/strategies/ and use consensus signal. "
             "This is the default when --strategy is not specified.",
    )
    parser.add_argument(
        "--symbol",
        default=None,
        help="Process a single symbol only (default: all instruments).",
    )
    args = parser.parse_args()

    ensure_data_dirs()

    # Load environment config and create LLM services
    config_path = ROOT / "config" / "environments" / "local.yaml"
    try:
        with open(config_path) as f:
            env_config = yaml.safe_load(f) or {}
    except OSError:
        logger.warning("Could not load local.yaml — LLM will use stub client")
        env_config = {}

    llm_client = create_llm_client(env_config)
    explanation_svc = ExplanationService(llm_client)
    decision_svc = DecisionService(llm_client)
    logger.info("LLM provider: %s", env_config.get("llm", {}).get("provider", "gemini"))

    # Determine run mode:
    #   - Single-strategy: --strategy is explicitly provided
    #   - Multi-strategy:  --multi flag OR no --strategy specified (default)
    use_multi = args.multi or (args.strategy is None)

    instruments = load_instruments(INSTRUMENTS_CONFIG)
    if not instruments:
        logger.error("No instruments found in %s", INSTRUMENTS_CONFIG)
        sys.exit(1)

    if args.symbol:
        instruments = [i for i in instruments if i["symbol"] == args.symbol]
        if not instruments:
            logger.error("Symbol %s not found in instruments.yaml", args.symbol)
            sys.exit(1)

    rows = []
    failed: list[str] = []

    if use_multi:
        # --- Multi-strategy mode ---
        logger.info("Mode: multi-strategy (consensus vote)")
        logger.info("Loading all strategies from %s", STRATEGIES_CONFIG_DIR)
        strategies = _load_all_strategies(STRATEGIES_CONFIG_DIR)
        if not strategies:
            logger.error("No strategies could be loaded from %s", STRATEGIES_CONFIG_DIR)
            sys.exit(1)
        if PRIMARY_STRATEGY_NAME not in strategies:
            logger.warning(
                "Primary strategy '%s' not found — stop/target levels will be unavailable",
                PRIMARY_STRATEGY_NAME,
            )

        logger.info("Running signals — %d instrument(s), %d strategy/strategies", len(instruments), len(strategies))
        logger.info("=" * 60)

        for instrument in instruments:
            row = process_instrument_multi(
                instrument,
                strategies,
                PRIMARY_STRATEGY_NAME,
                explanation_svc,
                decision_svc,
            )
            rows.append(row)
            if row["status"] not in ("ok", "data_missing"):
                failed.append(instrument["symbol"])

    else:
        # --- Single-strategy mode (--strategy explicitly specified) ---
        strategy_path = Path(args.strategy)
        logger.info("Mode: single-strategy (%s)", strategy_path)
        try:
            strategy = load_strategy(strategy_path)
        except Exception as exc:
            logger.error("Failed to load strategy: %s", exc)
            sys.exit(1)

        logger.info("Running signals — %d instrument(s)", len(instruments))
        logger.info("=" * 60)

        for instrument in instruments:
            row = process_instrument(instrument, strategy, explanation_svc, decision_svc)
            rows.append(row)
            if row["status"] not in ("ok", "data_missing"):
                failed.append(instrument["symbol"])

    logger.info("=" * 60)

    snapshot = pd.DataFrame(rows)
    write_snapshot_atomic(snapshot)

    ok_count = sum(1 for r in rows if r["status"] == "ok")
    missing_count = sum(1 for r in rows if r["status"] == "data_missing")
    logger.info(
        "Complete — %d ok, %d data_missing, %d errors",
        ok_count,
        missing_count,
        len(failed),
    )

    if failed:
        logger.warning("Failed instruments: %s", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()
