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
    curated_df.to_parquet(curated_path, index=False)

    return raw_path, curated_path, curated_df
