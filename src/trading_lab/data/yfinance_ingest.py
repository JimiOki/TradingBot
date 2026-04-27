from pathlib import Path

import pandas as pd
import yfinance as yf

from trading_lab.data.models import MarketDataRequest
from trading_lab.data.transforms import normalize_yfinance_daily
from trading_lab.paths import CURATED_DATA_DIR, RAW_DATA_DIR, ensure_data_dirs


def download_market_data(request: MarketDataRequest) -> pd.DataFrame:
    """Download source data for a market-data request."""
    df = yf.download(
        request.symbol,
        period=request.period,
        interval=request.interval,
        auto_adjust=request.adjusted,
        progress=False,
    )
    if df.empty:
        raise RuntimeError(f"No data downloaded for {request.symbol}.")
    return df


def build_output_paths(symbol: str, interval: str, source: str) -> tuple[Path, Path]:
    file_name = f"{symbol.lower()}_{interval}_{source}.parquet"
    return RAW_DATA_DIR / file_name, CURATED_DATA_DIR / file_name


def ingest_yfinance_daily(request: MarketDataRequest) -> tuple[Path, Path, pd.DataFrame]:
    """Download, normalize, and persist market data to raw and curated parquet files."""
    ensure_data_dirs()
    raw_path, curated_path = build_output_paths(request.symbol, request.interval, request.source)

    raw_df = download_market_data(request)
    raw_df.to_parquet(raw_path)

    curated_df = normalize_yfinance_daily(raw_df, symbol=request.symbol, source=request.source)
    curated_df.to_parquet(curated_path, index=True)

    return raw_path, curated_path, curated_df


def fetch_news(symbol: str, max_headlines: int = 5) -> list[dict]:
    """Fetch recent news headlines for a symbol via yfinance.

    REQ-LLM-008: News headlines are fetched per instrument and included
    in SignalContext for LLM explanation and decision generation.

    Args:
        symbol:        Instrument symbol (e.g. 'GC=F').
        max_headlines: Maximum number of headlines to return.

    Returns:
        List of dicts with {title, source, timestamp}. Empty list on error.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)
    try:
        ticker = yf.Ticker(symbol)
        raw_news = ticker.news or []
        headlines = []
        for item in raw_news[:max_headlines]:
            headlines.append({
                "title": item.get("title", ""),
                "source": item.get("publisher", ""),
                "timestamp": item.get("providerPublishTime", ""),
            })
        return headlines
    except Exception as exc:
        _log.debug("News fetch failed for %s: %s", symbol, exc)
        return []
