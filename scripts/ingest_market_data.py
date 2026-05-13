"""Ingest daily market data for all instruments in config/instruments.yaml.

Usage:
    python scripts/ingest_market_data.py
    python scripts/ingest_market_data.py --period 1y
    python scripts/ingest_market_data.py --symbol GC=F

This script:
1. Reads all instruments from config/instruments.yaml
2. Downloads daily OHLCV data from yfinance for each
3. Saves raw data to data/raw/<symbol>_1d_yfinance.parquet
4. Saves curated data to data/curated/<symbol>_1d_yfinance.parquet
5. Logs success/failure for each instrument

Run this daily after market close to keep data fresh.
"""
import argparse
import logging
import sys
from pathlib import Path


# Ensure src/ is importable when running as a script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from trading_lab.config.loader import load_instruments
from trading_lab.data.models import MarketDataRequest
from trading_lab.data.yfinance_ingest import ingest_yfinance_daily
from trading_lab.logging_config import setup_logging
from trading_lab.paths import INSTRUMENTS_CONFIG, ensure_data_dirs

setup_logging()
logger = logging.getLogger("ingest")




def ingest_instrument(instrument: dict, period: str) -> bool:
    """Ingest a single instrument. Returns True on success, False on failure."""
    symbol = instrument["symbol"]
    name = instrument.get("name", symbol)
    adjusted = instrument.get("adjusted_prices", False)

    logger.info("Ingesting %s (%s) — period=%s", name, symbol, period)

    try:
        request = MarketDataRequest(
            symbol=symbol,
            period=period,
            interval="1d",
            adjusted=adjusted,
        )
        raw_path, curated_path, df = ingest_yfinance_daily(request)
        logger.info(
            "  ✓ %s — %d bars, %s → %s",
            symbol,
            len(df),
            df.index.min().date(),
            df.index.max().date(),
        )
        logger.info("    Raw:     %s", raw_path)
        logger.info("    Curated: %s", curated_path)
        return True

    except Exception as e:
        logger.error("  ✗ %s — FAILED: %s", symbol, e)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest market data for all instruments.")
    parser.add_argument(
        "--period",
        default="2y",
        help="yfinance period string (default: 2y). Options: 1mo, 3mo, 6mo, 1y, 2y, 5y, max",
    )
    parser.add_argument(
        "--symbol",
        default=None,
        help="Ingest a single symbol only (e.g. GC=F). Defaults to all instruments.",
    )
    args = parser.parse_args()

    ensure_data_dirs()

    instruments = load_instruments(INSTRUMENTS_CONFIG)
    if not instruments:
        logger.error("No instruments found in %s", INSTRUMENTS_CONFIG)
        sys.exit(1)

    if args.symbol:
        instruments = [i for i in instruments if i["symbol"] == args.symbol]
        if not instruments:
            logger.error("Symbol %s not found in instruments.yaml", args.symbol)
            sys.exit(1)

    logger.info("Starting ingestion — %d instrument(s), period=%s", len(instruments), args.period)
    logger.info("=" * 60)

    results = []
    for instrument in instruments:
        success = ingest_instrument(instrument, period=args.period)
        results.append((instrument["symbol"], success))

    logger.info("=" * 60)
    passed = sum(1 for _, ok in results if ok)
    failed = len(results) - passed
    logger.info("Ingestion complete — %d succeeded, %d failed", passed, failed)

    if failed > 0:
        logger.warning("Failed instruments: %s", [s for s, ok in results if not ok])
        sys.exit(1)


if __name__ == "__main__":
    main()
