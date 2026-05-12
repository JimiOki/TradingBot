"""Ingest daily OHLCV data from the IG REST API.

Fetches historical prices via GET /prices/{epic} and normalises
bid/ask into midpoint OHLCV bars matching the curated bar schema.

Uses the LIVE IG account for data fetching (demo API often returns
incomplete data for historical prices).
"""
import logging
import os
from pathlib import Path

import pandas as pd
import requests

from trading_lab.data.transforms import CURATED_COLUMNS
from trading_lab.paths import CURATED_DATA_DIR, RAW_DATA_DIR, ensure_data_dirs

logger = logging.getLogger(__name__)

# IG REST API base URLs
_IG_LIVE_URL = "https://api.ig.com/gateway/deal"
_IG_DEMO_URL = "https://demo-api.ig.com/gateway/deal"


def _get_ig_session() -> tuple[str, dict]:
    """Authenticate with IG and return (base_url, headers).

    Prefers LIVE credentials (IG_LIVE_*) for data fetching.
    Falls back to demo credentials if live are not set.
    """
    # Try live first
    api_key = os.environ.get("IG_LIVE_API_KEY", "")
    username = os.environ.get("IG_LIVE_USERNAME", "")
    password = os.environ.get("IG_LIVE_PASSWORD", "")
    base_url = _IG_LIVE_URL

    if not all([api_key, username, password]):
        # Fall back to demo
        api_key = os.environ.get("IG_API_KEY", "")
        username = os.environ.get("IG_USERNAME", "")
        password = os.environ.get("IG_PASSWORD", "")
        base_url = _IG_DEMO_URL if os.environ.get("IG_DEMO", "").lower() == "true" else _IG_LIVE_URL

    if not all([api_key, username, password]):
        raise RuntimeError(
            "IG credentials missing. Set IG_LIVE_API_KEY/IG_LIVE_USERNAME/IG_LIVE_PASSWORD "
            "or IG_API_KEY/IG_USERNAME/IG_PASSWORD in .env"
        )

    # Create session (v3 auth)
    auth_headers = {
        "X-IG-API-KEY": api_key,
        "Content-Type": "application/json; charset=UTF-8",
        "Accept": "application/json; charset=UTF-8",
        "Version": "3",
    }
    auth_body = {
        "identifier": username,
        "password": password,
    }

    resp = requests.post(f"{base_url}/session", json=auth_body, headers=auth_headers)
    resp.raise_for_status()

    # Extract tokens from response headers
    cst = resp.headers.get("CST", "")
    security_token = resp.headers.get("X-SECURITY-TOKEN", "")

    # Also check for OAuth token in response body
    session_headers = {
        "X-IG-API-KEY": api_key,
        "CST": cst,
        "X-SECURITY-TOKEN": security_token,
        "Content-Type": "application/json; charset=UTF-8",
        "Accept": "application/json; charset=UTF-8",
    }

    logger.info("IG session created for data ingestion (base_url=%s)", base_url)
    return base_url, session_headers


def fetch_ig_daily_prices(
    epic: str,
    max_bars: int = 500,
    base_url: str | None = None,
    headers: dict | None = None,
) -> pd.DataFrame:
    """Fetch daily OHLCV from IG for a single epic.

    Args:
        epic: IG epic identifier (e.g. "CS.D.USCGC.TODAY.IP").
        max_bars: Maximum number of bars to fetch (IG allows up to 500 for DAY).
        base_url: IG API base URL (if None, creates a new session).
        headers: Authenticated headers (if None, creates a new session).

    Returns:
        DataFrame with columns: open, high, low, close, volume
        and a UTC DatetimeIndex named 'timestamp'.
    """
    if base_url is None or headers is None:
        base_url, headers = _get_ig_session()

    url = f"{base_url}/prices/{epic}"
    params = {
        "resolution": "DAY",
        "max": max_bars,
        "pageSize": 0,  # return all in one page
    }

    req_headers = dict(headers)
    req_headers["Version"] = "3"

    resp = requests.get(url, params=params, headers=req_headers)
    resp.raise_for_status()
    data = resp.json()

    prices = data.get("prices", [])
    if not prices:
        raise RuntimeError(f"No price data returned from IG for epic={epic}")

    rows = []
    for bar in prices:
        snapshot_time = bar.get("snapshotTime", "")
        # snapshotTime is like "2024/05/10 00:00:00" or ISO format
        bid_open = bar.get("openPrice", {}).get("bid")
        bid_high = bar.get("highPrice", {}).get("bid")
        bid_low = bar.get("lowPrice", {}).get("bid")
        bid_close = bar.get("closePrice", {}).get("bid")

        ask_open = bar.get("openPrice", {}).get("ask")
        ask_high = bar.get("highPrice", {}).get("ask")
        ask_low = bar.get("lowPrice", {}).get("ask")
        ask_close = bar.get("closePrice", {}).get("ask")

        volume = bar.get("lastTradedVolume", 0) or 0

        # Compute midpoints (average of bid and ask)
        def mid(b, a):
            if b is not None and a is not None:
                return (float(b) + float(a)) / 2.0
            if b is not None:
                return float(b)
            if a is not None:
                return float(a)
            return None

        rows.append({
            "timestamp": snapshot_time,
            "open": mid(bid_open, ask_open),
            "high": mid(bid_high, ask_high),
            "low": mid(bid_low, ask_low),
            "close": mid(bid_close, ask_close),
            "volume": float(volume),
        })

    df = pd.DataFrame(rows)

    # Parse timestamps — IG uses "2024/05/10 00:00:00" format
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed", utc=True)
    df = df.set_index("timestamp")
    df = df.sort_index()
    df = df.loc[~df.index.duplicated(keep="last")]

    logger.debug("Fetched %d daily bars from IG for %s", len(df), epic)
    return df


def normalize_ig_daily(
    raw_df: pd.DataFrame,
    symbol: str,
) -> pd.DataFrame:
    """Normalise IG daily DataFrame into the curated bar schema.

    Args:
        raw_df: DataFrame from fetch_ig_daily_prices (midpoint OHLCV).
        symbol: Instrument symbol (e.g. 'GC=F').

    Returns:
        Normalised DataFrame with DatetimeIndex (UTC) and CURATED_COLUMNS.
    """
    df = raw_df.copy()

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
    df["source"] = "ig"
    df["adjusted"] = False  # spreadbet prices are not adjusted

    # Select and order canonical columns
    df = df[CURATED_COLUMNS]

    # Sort and deduplicate
    df = df.sort_index()
    df = df.loc[~df.index.duplicated(keep="last")]

    logger.debug("Normalised %d bars for %s (source=ig)", len(df), symbol)
    return df


def build_output_paths(symbol: str, interval: str = "1d") -> tuple[Path, Path]:
    """Return (raw_path, curated_path) for IG-sourced data."""
    file_name = f"{symbol.lower()}_{interval}_ig.parquet"
    return RAW_DATA_DIR / file_name, CURATED_DATA_DIR / file_name


def _fetch_yahoo_volume(symbol: str, max_bars: int) -> pd.Series | None:
    """Fetch real exchange volume from Yahoo Finance.

    Returns a Series indexed by date (UTC) with volume values,
    or None if the fetch fails.
    """
    try:
        import yfinance as yf

        # Map max_bars to a yfinance period
        if max_bars <= 30:
            period = "1mo"
        elif max_bars <= 90:
            period = "3mo"
        elif max_bars <= 180:
            period = "6mo"
        elif max_bars <= 365:
            period = "1y"
        else:
            period = "2y"

        df = yf.download(symbol, period=period, interval="1d", progress=False)
        if df.empty:
            return None

        # Flatten MultiIndex columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]

        if "Volume" not in df.columns:
            return None

        vol = df["Volume"].copy()
        vol.index = pd.to_datetime(vol.index)
        if vol.index.tz is None:
            vol.index = vol.index.tz_localize("UTC")
        else:
            vol.index = vol.index.tz_convert("UTC")
        # Normalize to date-only for matching (drop time component)
        vol.index = vol.index.normalize()
        vol.index.name = "timestamp"
        return vol
    except Exception as exc:
        logger.debug("Yahoo volume fetch failed for %s: %s", symbol, exc)
        return None


def ingest_ig_daily(
    symbol: str,
    epic: str,
    max_bars: int = 500,
    base_url: str | None = None,
    headers: dict | None = None,
) -> tuple[Path, Path, pd.DataFrame]:
    """Download, normalize, and persist IG daily data.

    OHLC prices come from IG (bid/ask midpoints). Volume is overlaid
    from Yahoo Finance (real exchange volume) when available, falling
    back to IG's platform volume.

    Args:
        symbol: Instrument symbol (e.g. 'GC=F').
        epic: IG epic (e.g. 'CS.D.USCGC.TODAY.IP').
        max_bars: Max daily bars to fetch.
        base_url: Pre-authenticated IG base URL (optional).
        headers: Pre-authenticated IG headers (optional).

    Returns:
        (raw_path, curated_path, curated_df)
    """
    ensure_data_dirs()
    raw_path, curated_path = build_output_paths(symbol)

    raw_df = fetch_ig_daily_prices(epic, max_bars=max_bars, base_url=base_url, headers=headers)
    raw_df.to_parquet(raw_path)

    curated_df = normalize_ig_daily(raw_df, symbol=symbol)

    # Overlay real exchange volume from Yahoo
    yahoo_vol = _fetch_yahoo_volume(symbol, max_bars)
    if yahoo_vol is not None:
        # Match on normalized date (IG timestamps may have time components)
        curated_dates = curated_df.index.normalize()
        matched = 0
        for i, dt in enumerate(curated_dates):
            if dt in yahoo_vol.index:
                curated_df.iloc[i, curated_df.columns.get_loc("volume")] = float(yahoo_vol[dt])
                matched += 1
        if matched > 0:
            logger.info("  Overlaid Yahoo volume for %s: %d/%d bars matched", symbol, matched, len(curated_df))
        else:
            logger.debug("  No Yahoo volume dates matched for %s", symbol)

    curated_df.to_parquet(curated_path, index=True)

    return raw_path, curated_path, curated_df
