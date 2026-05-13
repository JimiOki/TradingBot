"""Ingest daily market data for all instruments in config/instruments.yaml.

Usage:
    python scripts/ingest_market_data.py
    python scripts/ingest_market_data.py --max-bars 200
    python scripts/ingest_market_data.py --symbol GC=F

Primary source is IG REST API (bid/ask midpoints). If IG fails (403 rate
limit, auth error, etc.) the script falls back to Yahoo Finance so the
pipeline never stalls.

Default --max-bars is 10 for daily cron runs (appends to existing history).
Use --max-bars 500 for initial bulk loads.

Output:
    data/raw/<symbol>_1d_ig.parquet     (IG raw data)
    data/curated/<symbol>_1d_ig.parquet (normalised bars)
    — or on fallback —
    data/raw/<symbol>_1d_yfinance.parquet
    data/curated/<symbol>_1d_yfinance.parquet
"""
import argparse
import logging
import sys
from pathlib import Path


# Ensure src/ is importable when running as a script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from trading_lab.config.loader import load_instruments
from trading_lab.data.ig_ingest import _get_ig_session, ingest_ig_daily
from trading_lab.data.models import MarketDataRequest
from trading_lab.data.yfinance_ingest import ingest_yfinance_daily
from trading_lab.logging_config import setup_logging
from trading_lab.paths import INSTRUMENTS_CONFIG, ensure_data_dirs

setup_logging()
logger = logging.getLogger("ingest")


def _ingest_via_yahoo(instrument: dict) -> bool:
    """Fallback: ingest via Yahoo Finance. Returns True on success."""
    symbol = instrument["symbol"]
    adjusted = instrument.get("adjusted_prices", False)
    try:
        request = MarketDataRequest(
            symbol=symbol,
            period="2y",
            interval="1d",
            adjusted=adjusted,
        )
        raw_path, curated_path, df = ingest_yfinance_daily(request)
        logger.info(
            "  ✓ %s (Yahoo fallback) — %d bars, %s → %s",
            symbol, len(df), df.index.min().date(), df.index.max().date(),
        )
        return True
    except Exception as exc:
        logger.error("  ✗ %s — Yahoo fallback also FAILED: %s", symbol, exc)
        return False


def ingest_instrument(
    instrument: dict,
    max_bars: int,
    base_url: str | None,
    headers: dict | None,
) -> bool:
    """Ingest a single instrument. Tries IG first, falls back to Yahoo."""
    symbol = instrument["symbol"]
    name = instrument.get("name", symbol)
    epic = instrument.get("ig_epic", "")

    if not epic:
        logger.warning("  %s — no ig_epic, using Yahoo", symbol)
        return _ingest_via_yahoo(instrument)

    logger.info("Ingesting %s (%s) — epic=%s max_bars=%d", name, symbol, epic, max_bars)

    try:
        raw_path, curated_path, df = ingest_ig_daily(
            symbol=symbol,
            epic=epic,
            max_bars=max_bars,
            base_url=base_url,
            headers=headers,
        )
        logger.info(
            "  ✓ %s — %d bars, %s → %s",
            symbol, len(df), df.index.min().date(), df.index.max().date(),
        )
        return True

    except Exception as e:
        logger.warning("  ✗ %s — IG failed: %s — falling back to Yahoo", symbol, e)
        return _ingest_via_yahoo(instrument)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest market data for all instruments.")
    parser.add_argument(
        "--max-bars",
        type=int,
        default=10,
        help="Maximum number of daily bars to fetch from IG (default: 10). "
             "Use 500 for initial bulk load.",
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

    # Create a single IG session for all instruments
    base_url: str | None = None
    headers: dict | None = None
    try:
        base_url, headers = _get_ig_session()
    except Exception as exc:
        logger.warning("Failed to create IG session: %s — will use Yahoo for all", exc)

    logger.info("Starting ingestion — %d instrument(s), max_bars=%d", len(instruments), args.max_bars)
    logger.info("=" * 60)

    results = []
    for instrument in instruments:
        success = ingest_instrument(instrument, args.max_bars, base_url, headers)
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
