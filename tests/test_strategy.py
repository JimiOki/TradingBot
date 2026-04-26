"""Tests for src/trading_lab/strategies/"""
import numpy as np
import pandas as pd
import pytest

from trading_lab.strategies.base import REQUIRED_SIGNAL_COLUMNS
from trading_lab.strategies.sma_cross import SmaCrossStrategy


def _make_bars(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """Synthetic daily OHLCV bars with UTC DatetimeIndex."""
    np.random.seed(seed)
    dates = pd.date_range("2023-01-01", periods=n, freq="B", tz="UTC")
    close = 100 * (1 + np.random.randn(n) * 0.01).cumprod()
    open_ = close * (1 + np.random.randn(n) * 0.002)
    high = np.maximum(close, open_) * (1 + np.abs(np.random.randn(n) * 0.003))
    low = np.minimum(close, open_) * (1 - np.abs(np.random.randn(n) * 0.003))
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close},
        index=dates,
    )


def _crossover_bars() -> pd.DataFrame:
    """Bars engineered so fast SMA crosses above slow SMA at a known point.

    First 60 bars: flat/falling (fast < slow).
    Next 100 bars: strongly rising (fast > slow after warmup).
    """
    n = 160
    dates = pd.date_range("2023-01-01", periods=n, freq="B", tz="UTC")
    prices = np.concatenate(
        [np.linspace(110, 100, 60), np.linspace(100, 160, 100)]
    )
    high = prices * 1.002
    low = prices * 0.998
    return pd.DataFrame(
        {"open": prices, "high": high, "low": low, "close": prices},
        index=dates,
    )


# ---------------------------------------------------------------------------
# SmaCrossStrategy constructor
# ---------------------------------------------------------------------------


def test_fast_ge_slow_raises():
    with pytest.raises(ValueError):
        SmaCrossStrategy(fast_window=50, slow_window=20)


def test_fast_equal_slow_raises():
    with pytest.raises(ValueError):
        SmaCrossStrategy(fast_window=20, slow_window=20)


def test_default_construction_succeeds():
    s = SmaCrossStrategy()
    assert s.fast_window < s.slow_window


# ---------------------------------------------------------------------------
# generate_signals — output contract
# ---------------------------------------------------------------------------


def test_output_has_all_required_columns(sample_bars):
    signals = SmaCrossStrategy().generate_signals(sample_bars)
    for col in REQUIRED_SIGNAL_COLUMNS:
        assert col in signals.columns, f"Missing column: {col}"


def test_output_length_matches_input(sample_bars):
    signals = SmaCrossStrategy().generate_signals(sample_bars)
    assert len(signals) == len(sample_bars)


def test_signal_values_in_valid_set(sample_bars):
    signals = SmaCrossStrategy().generate_signals(sample_bars)
    valid = {-1, 0, 1}
    assert set(signals["signal"].dropna().unique()).issubset(valid)


def test_position_change_column_present(sample_bars):
    signals = SmaCrossStrategy().generate_signals(sample_bars)
    assert "position_change" in signals.columns


def test_missing_close_column_raises():
    bars = _make_bars()
    bars = bars.drop(columns=["close"])
    with pytest.raises(ValueError, match="close"):
        SmaCrossStrategy().generate_signals(bars)


def test_non_datetime_index_raises():
    bars = _make_bars()
    bars = bars.reset_index(drop=True)
    with pytest.raises(ValueError):
        SmaCrossStrategy().generate_signals(bars)


# ---------------------------------------------------------------------------
# generate_signals — signal logic
# ---------------------------------------------------------------------------


def test_rising_market_produces_long_signal():
    """Strongly trending-up market should produce long signals (RSI filter disabled)."""
    bars = _crossover_bars()
    # rsi_overbought=100 disables the RSI filter so crossover drives the signal
    signals = SmaCrossStrategy(
        fast_window=10, slow_window=30, rsi_overbought=100
    ).generate_signals(bars)
    assert (signals["signal"] == 1).any()


def test_falling_market_produces_short_signal():
    """Strongly trending-down market should produce short signals (RSI filter disabled)."""
    n = 100
    dates = pd.date_range("2023-01-01", periods=n, freq="B", tz="UTC")
    prices = np.linspace(150, 80, n)
    bars = pd.DataFrame(
        {"open": prices, "high": prices * 1.002, "low": prices * 0.998, "close": prices},
        index=dates,
    )
    # rsi_oversold=0 disables the short RSI filter
    signals = SmaCrossStrategy(
        fast_window=10, slow_window=30, rsi_oversold=0
    ).generate_signals(bars)
    assert (signals["signal"] == -1).any()


def test_rsi_filter_suppresses_overbought_buy():
    """When RSI > overbought threshold, a long raw signal must be suppressed to 0."""
    # Use a very high overbought threshold of 10 to force all non-zero RSI to be "overbought"
    bars = _crossover_bars()
    signals_unfiltered = SmaCrossStrategy(
        fast_window=10, slow_window=30, rsi_overbought=100
    ).generate_signals(bars)
    signals_filtered = SmaCrossStrategy(
        fast_window=10, slow_window=30, rsi_overbought=1
    ).generate_signals(bars)
    # With threshold=1 (virtually nothing passes), long signals should be heavily suppressed
    unfiltered_longs = (signals_unfiltered["signal"] == 1).sum()
    filtered_longs = (signals_filtered["signal"] == 1).sum()
    assert filtered_longs < unfiltered_longs


# ---------------------------------------------------------------------------
# Stop loss and take profit
# ---------------------------------------------------------------------------


def test_stop_loss_below_close_for_long_signal(sample_bars):
    signals = SmaCrossStrategy().generate_signals(sample_bars)
    long_bars = signals[signals["signal"] == 1].dropna(subset=["stop_loss_level"])
    if not long_bars.empty:
        assert (long_bars["stop_loss_level"] < long_bars["close"]).all()


def test_take_profit_above_close_for_long_signal(sample_bars):
    signals = SmaCrossStrategy().generate_signals(sample_bars)
    long_bars = signals[signals["signal"] == 1].dropna(subset=["take_profit_level"])
    if not long_bars.empty:
        assert (long_bars["take_profit_level"] > long_bars["close"]).all()


def test_stop_loss_above_close_for_short_signal(sample_bars):
    signals = SmaCrossStrategy().generate_signals(sample_bars)
    short_bars = signals[signals["signal"] == -1].dropna(subset=["stop_loss_level"])
    if not short_bars.empty:
        assert (short_bars["stop_loss_level"] > short_bars["close"]).all()
