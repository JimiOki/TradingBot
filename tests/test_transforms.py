"""Tests for src/trading_lab/data/transforms.py"""
import numpy as np
import pandas as pd
import pytest

from trading_lab.data.transforms import CURATED_COLUMNS, normalize_yfinance_daily


def _make_raw(n: int = 50, tz=None) -> pd.DataFrame:
    """Minimal flat-column raw DataFrame resembling yfinance output."""
    dates = pd.date_range("2023-01-01", periods=n, freq="B", tz=tz)
    np.random.seed(0)
    close = 100.0 + np.cumsum(np.random.randn(n))
    return pd.DataFrame(
        {
            "Open": close * 0.999,
            "High": close * 1.002,
            "Low": close * 0.997,
            "Close": close,
            "Volume": np.ones(n) * 1_000_000,
        },
        index=dates,
    )


def test_produces_all_curated_columns():
    df = normalize_yfinance_daily(_make_raw(), symbol="GC=F")
    for col in CURATED_COLUMNS:
        assert col in df.columns, f"Missing column: {col}"


def test_timestamp_index_is_utc_aware():
    df = normalize_yfinance_daily(_make_raw(), symbol="GC=F")
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.tz is not None
    assert str(df.index.tz) == "UTC"


def test_tz_naive_input_is_localised_to_utc():
    df = normalize_yfinance_daily(_make_raw(tz=None), symbol="GC=F")
    assert str(df.index.tz) == "UTC"


def test_non_utc_tz_input_is_converted_to_utc():
    df = normalize_yfinance_daily(_make_raw(tz="America/New_York"), symbol="GC=F")
    assert str(df.index.tz) == "UTC"


def test_adjusted_true_written_to_column():
    df = normalize_yfinance_daily(_make_raw(), symbol="GC=F", adjusted=True)
    assert df["adjusted"].all()


def test_adjusted_false_written_to_column():
    df = normalize_yfinance_daily(_make_raw(), symbol="GC=F", adjusted=False)
    assert not df["adjusted"].any()


def test_symbol_column_matches_argument():
    df = normalize_yfinance_daily(_make_raw(), symbol="CL=F")
    assert (df["symbol"] == "CL=F").all()


def test_source_column_matches_argument():
    df = normalize_yfinance_daily(_make_raw(), symbol="GC=F", source="test_source")
    assert (df["source"] == "test_source").all()


def test_multiindex_columns_are_flattened():
    raw = _make_raw()
    raw.columns = pd.MultiIndex.from_tuples([(c, "GC=F") for c in raw.columns])
    df = normalize_yfinance_daily(raw, symbol="GC=F")
    assert "close" in df.columns


def test_adj_close_replaces_close_when_adjusted_true():
    raw = _make_raw()
    raw.columns = [c.lower() for c in raw.columns]
    adj_values = raw["close"].values * 1.05
    raw["adj close"] = adj_values
    df = normalize_yfinance_daily(raw, symbol="GC=F", adjusted=True)
    assert np.allclose(df["close"].values, adj_values)


def test_adj_close_dropped_when_adjusted_false():
    raw = _make_raw()
    raw.columns = [c.lower() for c in raw.columns]
    original_close = raw["close"].values.copy()
    raw["adj close"] = raw["close"] * 1.05
    df = normalize_yfinance_daily(raw, symbol="GC=F", adjusted=False)
    assert np.allclose(df["close"].values, original_close)


def test_missing_required_column_raises():
    raw = _make_raw().drop(columns=["Close"])
    with pytest.raises(ValueError, match="missing required columns"):
        normalize_yfinance_daily(raw, symbol="GC=F")


def test_output_sorted_ascending():
    raw = _make_raw()
    raw = raw.iloc[::-1]  # reverse order
    df = normalize_yfinance_daily(raw, symbol="GC=F")
    assert df.index.is_monotonic_increasing


def test_duplicate_index_rows_deduplicated():
    raw = _make_raw(n=10)
    raw = pd.concat([raw, raw.iloc[:2]])
    df = normalize_yfinance_daily(raw, symbol="GC=F")
    assert df.index.is_unique
