"""Data transformation utilities for the trading-lab data layer.

Responsibility: convert source-shaped data into the project's normalised
bar schema. No I/O, no network calls, no strategy logic.

Normalised bar schema
---------------------
timestamp  : DatetimeTZDtype (UTC) — index
open       : float64
high       : float64
low        : float64
close      : float64
volume     : float64
symbol     : str
source     : str
adjusted   : bool
"""
import logging

import pandas as pd

logger = logging.getLogger(__name__)

# Canonical column order for curated Parquet files
CURATED_COLUMNS = ["open", "high", "low", "close", "volume", "symbol", "source", "adjusted"]


def normalize_yfinance_daily(
    raw_df: pd.DataFrame,
    symbol: str,
    adjusted: bool = True,
    source: str = "yfinance",
) -> pd.DataFrame:
    """Normalise a raw yfinance daily DataFrame into the curated bar schema.

    Args:
        raw_df:   Raw DataFrame as returned by yfinance (MultiIndex or flat columns).
        symbol:   Instrument symbol (e.g. 'GC=F').
        adjusted: Whether prices are adjusted for corporate actions.
        source:   Data source identifier written into the output.

    Returns:
        Normalised DataFrame with DatetimeIndex (UTC) and CURATED_COLUMNS.
    """
    df = raw_df.copy()

    # Flatten MultiIndex columns produced by yfinance when download() is used
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0].lower() for col in df.columns]
    else:
        df.columns = [col.lower() for col in df.columns]

    # Rename yfinance column variants to canonical names
    rename_map = {
        "adj close": "close",
        "adj_close": "close",
    }
    df = df.rename(columns=rename_map)

    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Raw DataFrame is missing required columns: {missing}")

    # Ensure DatetimeIndex is UTC
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    df.index.name = "timestamp"

    # Add provenance columns
    df["symbol"] = symbol
    df["source"] = source
    df["adjusted"] = adjusted

    # Select and order canonical columns
    df = df[CURATED_COLUMNS]

    # Sort chronologically and drop duplicates
    df = df.sort_index().loc[~df.index.duplicated(keep="last")]

    logger.debug("Normalised %d bars for %s (adjusted=%s)", len(df), symbol, adjusted)
    return df
