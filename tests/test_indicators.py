"""Tests for src/trading_lab/features/indicators.py"""
import numpy as np
import pandas as pd
import pytest

from trading_lab.features.indicators import atr, macd, rsi, rolling_atr_average, sma, sma_gap_pct


def _prices(n: int = 100, seed: int = 0) -> pd.Series:
    np.random.seed(seed)
    return pd.Series(100.0 + np.cumsum(np.random.randn(n)))


# ---------------------------------------------------------------------------
# SMA
# ---------------------------------------------------------------------------

def test_sma_warmup_count_window_20():
    result = sma(_prices(100), window=20)
    assert result.isna().sum() == 19
    assert result.notna().sum() == 81


def test_sma_constant_series_equals_constant():
    prices = pd.Series([50.0] * 30)
    result = sma(prices, window=10)
    assert np.allclose(result.dropna(), 50.0)


def test_sma_window_zero_raises():
    with pytest.raises(ValueError):
        sma(_prices(), window=0)


def test_sma_does_not_modify_input():
    prices = _prices()
    original = prices.copy()
    sma(prices, window=10)
    pd.testing.assert_series_equal(prices, original)


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------

def test_rsi_values_in_valid_range():
    result = rsi(_prices(100), window=14)
    non_null = result.dropna()
    assert (non_null >= 0).all() and (non_null <= 100).all()


def test_rsi_rising_prices_high_value():
    # Strongly rising prices with occasional dips → RSI should be high (> 70)
    np.random.seed(7)
    daily_changes = np.random.randn(100) * 0.5 + 0.8  # mostly positive
    prices = pd.Series(100.0 + np.cumsum(daily_changes))
    result = rsi(prices, window=14)
    assert result.dropna().iloc[-1] > 70


def test_rsi_falling_prices_low_value():
    # Strongly falling prices with occasional bounces → RSI should be low (< 30)
    np.random.seed(7)
    daily_changes = np.random.randn(100) * 0.5 - 0.8  # mostly negative
    prices = pd.Series(200.0 + np.cumsum(daily_changes))
    result = rsi(prices, window=14)
    assert result.dropna().iloc[-1] < 30


def test_rsi_window_zero_raises():
    with pytest.raises(ValueError):
        rsi(_prices(), window=0)


def test_rsi_does_not_modify_input():
    prices = _prices()
    original = prices.copy()
    rsi(prices, window=14)
    pd.testing.assert_series_equal(prices, original)


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

def test_macd_output_has_required_columns():
    result = macd(_prices(100))
    assert "macd_line" in result.columns
    assert "signal_line" in result.columns
    assert "histogram" in result.columns


def test_macd_histogram_equals_line_minus_signal():
    result = macd(_prices(100))
    expected = result["macd_line"] - result["signal_line"]
    pd.testing.assert_series_equal(result["histogram"], expected, check_names=False)


def test_macd_output_length_matches_input():
    prices = _prices(80)
    result = macd(prices)
    assert len(result) == len(prices)


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------

def test_atr_values_are_positive():
    n = 60
    np.random.seed(1)
    close = 100 + np.cumsum(np.random.randn(n))
    high = close + np.abs(np.random.randn(n))
    low = close - np.abs(np.random.randn(n))
    result = atr(pd.Series(high), pd.Series(low), pd.Series(close), window=14)
    assert (result.dropna() > 0).all()


def test_atr_output_length_matches_input():
    n = 50
    s = pd.Series(np.ones(n) * 100.0)
    result = atr(s, s, s, window=14)
    assert len(result) == n


# ---------------------------------------------------------------------------
# rolling_atr_average
# ---------------------------------------------------------------------------

def test_rolling_atr_average_warmup():
    atr_series = pd.Series(np.ones(60))
    result = rolling_atr_average(atr_series, window=30)
    assert result.isna().sum() == 29
    assert result.notna().sum() == 31


# ---------------------------------------------------------------------------
# sma_gap_pct
# ---------------------------------------------------------------------------

def test_sma_gap_pct_positive_when_fast_above_slow():
    fast = pd.Series([110.0, 115.0])
    slow = pd.Series([100.0, 100.0])
    result = sma_gap_pct(fast, slow)
    assert (result > 0).all()


def test_sma_gap_pct_negative_when_fast_below_slow():
    fast = pd.Series([90.0])
    slow = pd.Series([100.0])
    result = sma_gap_pct(fast, slow)
    assert result.iloc[0] < 0


def test_sma_gap_pct_known_value():
    # (110 - 100) / 100 * 100 = 10.0
    fast = pd.Series([110.0])
    slow = pd.Series([100.0])
    result = sma_gap_pct(fast, slow)
    assert np.isclose(result.iloc[0], 10.0)
