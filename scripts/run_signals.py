"""Generate and persist a portfolio signal snapshot for all instruments.

REQ-SIG-007: Every computed Phase 1 signal must be written to a persisted
snapshot on disk before the dashboard reads it.

REQ-WATCH-002: Returns a consolidated signal summary across all instruments
by reading the latest persisted signal snapshot from disk.

Usage::

    python scripts/run_signals.py
    python scripts/run_signals.py --strategy config/strategies/sma_cross.yaml
    python scripts/run_signals.py --symbol GC=F

Output:
    data/signals/portfolio_snapshot.parquet  — one row per instrument

The snapshot is written atomically (temp file + rename) so the dashboard
never reads a partial file. Exit code is non-zero if any instrument failed.
"""
import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from trading_lab.audit import AuditAction, log_event
from trading_lab.config.loader import load_instruments
from trading_lab.logging_config import setup_logging
from trading_lab.paths import (
    CURATED_DATA_DIR,
    INSTRUMENTS_CONFIG,
    SIGNALS_DATA_DIR,
    ensure_data_dirs,
)
from trading_lab.strategies.loader import load_strategy

setup_logging()
logger = logging.getLogger("run_signals")

# Stable path the dashboard reads from.
SNAPSHOT_PATH = SIGNALS_DATA_DIR / "portfolio_snapshot.parquet"

# Columns carried through from the last signal bar to the snapshot.
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



def curated_path_for(symbol: str, timeframe: str, source: str) -> Path:
    """Return the curated Parquet path for an instrument.

    Matches the naming convention in yfinance_ingest.build_output_paths.
    """
    filename = f"{symbol.lower()}_{timeframe}_{source}.parquet"
    return CURATED_DATA_DIR / filename


def process_instrument(instrument: dict, strategy) -> dict:
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
        default=str(ROOT / "config" / "strategies" / "sma_cross.yaml"),
        help="Path to strategy YAML config (default: config/strategies/sma_cross.yaml).",
    )
    parser.add_argument(
        "--symbol",
        default=None,
        help="Process a single symbol only (default: all instruments).",
    )
    args = parser.parse_args()

    ensure_data_dirs()

    strategy_path = Path(args.strategy)
    logger.info("Loading strategy from %s", strategy_path)
    try:
        strategy = load_strategy(strategy_path)
    except Exception as exc:
        logger.error("Failed to load strategy: %s", exc)
        sys.exit(1)

    instruments = load_instruments(INSTRUMENTS_CONFIG)
    if not instruments:
        logger.error("No instruments found in %s", INSTRUMENTS_CONFIG)
        sys.exit(1)

    if args.symbol:
        instruments = [i for i in instruments if i["symbol"] == args.symbol]
        if not instruments:
            logger.error("Symbol %s not found in instruments.yaml", args.symbol)
            sys.exit(1)

    logger.info("Running signals — %d instrument(s)", len(instruments))
    logger.info("=" * 60)

    rows = []
    failed: list[str] = []

    for instrument in instruments:
        row = process_instrument(instrument, strategy)
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
