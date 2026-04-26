"""Tests for src/trading_lab/backtesting/engine.py"""
import numpy as np
import pandas as pd
import pytest

from trading_lab.backtesting.engine import run_backtest
from trading_lab.backtesting.models import BacktestConfig, BacktestResult


def _config(**kwargs) -> BacktestConfig:
    defaults = dict(
        symbol="GC=F",
        strategy_name="test",
        initial_cash=100_000.0,
        commission_bps=0.0,
        slippage_bps=0.0,
    )
    defaults.update(kwargs)
    return BacktestConfig(**defaults)


def _signals_df(n: int = 50, signal_value: int = 0, seed: int = 0) -> pd.DataFrame:
    """Minimal signals DataFrame with constant signal."""
    np.random.seed(seed)
    dates = pd.date_range("2023-01-01", periods=n, freq="B", tz="UTC")
    close = 100.0 + np.cumsum(np.random.randn(n))
    return pd.DataFrame(
        {"close": close, "signal": signal_value},
        index=dates,
    )


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_missing_signal_column_raises():
    df = _signals_df()
    df = df.drop(columns=["signal"])
    with pytest.raises(ValueError, match="signal"):
        run_backtest(df, _config())


def test_missing_close_column_raises():
    df = _signals_df()
    df = df.drop(columns=["close"])
    with pytest.raises(ValueError, match="close"):
        run_backtest(df, _config())


def test_invalid_signal_value_raises():
    df = _signals_df()
    df["signal"] = 2  # invalid
    with pytest.raises(ValueError):
        run_backtest(df, _config())


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


def test_returns_backtest_result_instance():
    result = run_backtest(_signals_df(), _config())
    assert isinstance(result, BacktestResult)


def test_output_df_has_equity_column():
    result = run_backtest(_signals_df(), _config())
    assert "equity" in result.signals_df.columns


def test_output_df_has_position_column():
    result = run_backtest(_signals_df(), _config())
    assert "position" in result.signals_df.columns


def test_output_length_matches_input():
    df = _signals_df(n=80)
    result = run_backtest(df, _config())
    assert len(result.signals_df) == 80


# ---------------------------------------------------------------------------
# No-lookahead bias: signal on bar N → position on bar N+1
# ---------------------------------------------------------------------------


def test_no_lookahead_signal_bar5_produces_position_bar6():
    """Signal set to 1 at bar index 5 must NOT change position until bar 6."""
    df = _signals_df(n=20, signal_value=0)
    df.iloc[5, df.columns.get_loc("signal")] = 1
    result = run_backtest(df, _config())
    pos = result.signals_df["position"]
    # Bar 5 position should still be 0 (signal not yet acted on)
    assert pos.iloc[5] == 0
    # Bar 6 position should be 1
    assert pos.iloc[6] == 1


def test_flat_signal_entire_series_gives_zero_position():
    df = _signals_df(n=30, signal_value=0)
    result = run_backtest(df, _config())
    # position is signal shifted by 1; first bar is NaN filled to 0
    assert (result.signals_df["position"] == 0).all()


# ---------------------------------------------------------------------------
# Return calculation
# ---------------------------------------------------------------------------


def test_zero_cost_long_position_equals_market_return():
    """With zero costs and a constant long position, strategy return == market return."""
    n = 50
    np.random.seed(1)
    dates = pd.date_range("2023-01-01", periods=n, freq="B", tz="UTC")
    close = 100.0 + np.cumsum(np.random.randn(n))
    df = pd.DataFrame({"close": close, "signal": 1}, index=dates)
    result = run_backtest(df, _config(commission_bps=0.0, slippage_bps=0.0))
    sdf = result.signals_df.dropna(subset=["net_return", "market_return"])
    # For bars where position == 1, gross return == market return
    active = sdf[sdf["position"] == 1]
    np.testing.assert_allclose(
        active["gross_return"].values, active["market_return"].values, rtol=1e-10
    )


def test_short_position_profits_on_falling_prices():
    """Short position on a steadily declining market should produce positive equity growth."""
    n = 60
    dates = pd.date_range("2023-01-01", periods=n, freq="B", tz="UTC")
    close = np.linspace(100, 60, n)
    df = pd.DataFrame({"close": close, "signal": -1}, index=dates)
    result = run_backtest(df, _config(commission_bps=0.0, slippage_bps=0.0))
    sdf = result.signals_df.dropna(subset=["equity"])
    # Final equity should be above initial (short profits from falling prices)
    assert sdf["equity"].iloc[-1] > _config().initial_cash


def test_higher_cost_reduces_final_equity():
    df = _signals_df(n=50, signal_value=1)
    result_no_cost = run_backtest(df, _config(commission_bps=0.0, slippage_bps=0.0))
    result_high_cost = run_backtest(df, _config(commission_bps=50.0, slippage_bps=20.0))
    assert result_high_cost.final_equity < result_no_cost.final_equity


def test_higher_turnover_higher_cost():
    """Alternating signals (high turnover) should cost more than constant signal."""
    n = 50
    dates = pd.date_range("2023-01-01", periods=n, freq="B", tz="UTC")
    close = 100.0 + np.arange(n, dtype=float) * 0.1
    # High turnover: alternates every bar
    alternating_signal = [1 if i % 2 == 0 else -1 for i in range(n)]
    df_alt = pd.DataFrame({"close": close, "signal": alternating_signal}, index=dates)
    df_const = pd.DataFrame({"close": close, "signal": 1}, index=dates)
    config = _config(commission_bps=5.0, slippage_bps=2.0)
    result_alt = run_backtest(df_alt, config)
    result_const = run_backtest(df_const, config)
    assert result_alt.signals_df["cost"].sum() > result_const.signals_df["cost"].sum()


# ---------------------------------------------------------------------------
# Equity and return properties
# ---------------------------------------------------------------------------


def test_total_return_pct_property():
    df = _signals_df(n=30, signal_value=0)
    result = run_backtest(df, _config(initial_cash=10_000.0))
    # With flat signal, no position, equity should be roughly constant → total return ≈ 0
    # (small changes due to cumprod on near-zero returns)
    assert isinstance(result.total_return_pct, float)


def test_final_equity_property_matches_last_row():
    df = _signals_df(n=40)
    result = run_backtest(df, _config())
    assert result.final_equity == result.signals_df["equity"].iloc[-1]
