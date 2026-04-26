"""Shared pytest fixtures for trading-lab tests."""
import pandas as pd
import numpy as np
import pytest
from pathlib import Path


@pytest.fixture
def sample_bars() -> pd.DataFrame:
    """200 bars of synthetic daily OHLCV data for testing."""
    np.random.seed(42)
    n = 200
    dates = pd.date_range("2023-01-01", periods=n, freq="B", tz="UTC")
    close = 100 * (1 + np.random.randn(n) * 0.01).cumprod()
    open_ = close * (1 + np.random.randn(n) * 0.002)
    high = np.maximum(close, open_) * (1 + np.abs(np.random.randn(n) * 0.003))
    low = np.minimum(close, open_) * (1 - np.abs(np.random.randn(n) * 0.003))
    volume = np.random.randint(1_000_000, 10_000_000, n).astype(float)
    return pd.DataFrame({
        "timestamp": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "symbol": "GC=F",
        "source": "yfinance",
        "adjusted": True,
    }).set_index("timestamp")
