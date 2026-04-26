"""Tests for src/trading_lab/backtesting/metrics.py"""
import numpy as np
import pandas as pd
import pytest

from trading_lab.backtesting.metrics import (
    cagr,
    compute_all,
    max_drawdown,
    profit_factor,
    sharpe_ratio,
    win_rate,
)
from trading_lab.backtesting.models import BacktestConfig, BacktestResult


def _config(**kwargs) -> BacktestConfig:
    defaults = dict(symbol="GC=F", strategy_name="test", initial_cash=100_000.0)
    defaults.update(kwargs)
    return BacktestConfig(**defaults)


def _make_result(net_returns: list[float], initial_cash: float = 100_000.0) -> BacktestResult:
    """Build a minimal BacktestResult from a net_return sequence."""
    n = len(net_returns)
    dates = pd.date_range("2023-01-01", periods=n, freq="B", tz="UTC")
    nr = pd.Series(net_returns, index=dates)
    equity = initial_cash * (1 + nr).cumprod()
    positions = pd.Series([1] * n, index=dates)
    df = pd.DataFrame(
        {"net_return": nr, "equity": equity, "position": positions},
        index=dates,
    )
    return BacktestResult(signals_df=df, config=_config(initial_cash=initial_cash))


# ---------------------------------------------------------------------------
# sharpe_ratio
# ---------------------------------------------------------------------------


def test_sharpe_constant_positive_returns():
    """Constant positive returns → positive Sharpe."""
    returns = pd.Series([0.001] * 252)
    assert sharpe_ratio(returns) > 0


def test_sharpe_constant_negative_returns():
    """Constant negative returns → negative Sharpe."""
    returns = pd.Series([-0.001] * 252)
    assert sharpe_ratio(returns) < 0


def test_sharpe_zero_std_returns_zero():
    """Zero variance returns → Sharpe = 0.0."""
    returns = pd.Series([0.0] * 100)
    assert sharpe_ratio(returns) == 0.0


def test_sharpe_known_value():
    """Verify annualisation: Sharpe = (mean/std) * sqrt(252)."""
    returns = pd.Series([0.001, 0.002] * 126)  # alternating → non-zero std
    expected = float((returns.mean() / returns.std()) * np.sqrt(252))
    assert abs(sharpe_ratio(returns) - expected) < 0.01


# ---------------------------------------------------------------------------
# max_drawdown
# ---------------------------------------------------------------------------


def test_max_drawdown_no_drawdown_returns_zero():
    equity = pd.Series([100.0, 110.0, 120.0, 130.0])
    assert max_drawdown(equity) == pytest.approx(0.0, abs=1e-10)


def test_max_drawdown_known_value():
    """Peak 100 → trough 75 → 25% drawdown."""
    equity = pd.Series([100.0, 90.0, 75.0, 80.0, 85.0])
    assert max_drawdown(equity) == pytest.approx(25.0, rel=1e-6)


def test_max_drawdown_is_positive():
    equity = pd.Series([100.0, 80.0, 60.0, 90.0])
    assert max_drawdown(equity) > 0


# ---------------------------------------------------------------------------
# win_rate
# ---------------------------------------------------------------------------


def test_win_rate_all_wins():
    returns = pd.Series([0.01, 0.02, 0.03])
    positions = pd.Series([1, 1, 1])
    assert win_rate(returns, positions) == pytest.approx(100.0)


def test_win_rate_all_losses():
    returns = pd.Series([-0.01, -0.02])
    positions = pd.Series([1, 1])
    assert win_rate(returns, positions) == pytest.approx(0.0)


def test_win_rate_half_wins():
    returns = pd.Series([0.01, -0.01, 0.02, -0.02])
    positions = pd.Series([1, 1, -1, -1])
    assert win_rate(returns, positions) == pytest.approx(50.0)


def test_win_rate_no_active_positions_returns_zero():
    returns = pd.Series([0.01, 0.02])
    positions = pd.Series([0, 0])
    assert win_rate(returns, positions) == 0.0


# ---------------------------------------------------------------------------
# cagr
# ---------------------------------------------------------------------------


def test_cagr_positive_growth():
    """2x equity over 252 bars ≈ 100% CAGR."""
    equity = pd.Series(np.linspace(100_000, 200_000, 252))
    result = cagr(equity, periods_per_year=252)
    assert result == pytest.approx(100.0, rel=0.05)


def test_cagr_flat_returns_zero():
    equity = pd.Series([100_000.0] * 252)
    result = cagr(equity, periods_per_year=252)
    assert result == pytest.approx(0.0, abs=1e-8)


def test_cagr_single_bar_returns_zero():
    equity = pd.Series([100_000.0])
    assert cagr(equity) == 0.0


def test_cagr_negative_growth_is_negative():
    equity = pd.Series(np.linspace(100_000, 50_000, 252))
    assert cagr(equity, periods_per_year=252) < 0


# ---------------------------------------------------------------------------
# profit_factor
# ---------------------------------------------------------------------------


def test_profit_factor_known_value():
    """Gross gains = 0.03, gross losses = 0.01 → profit factor = 3.0."""
    returns = pd.Series([0.01, 0.02, -0.01])
    assert profit_factor(returns) == pytest.approx(3.0, rel=1e-6)


def test_profit_factor_no_losses_returns_inf():
    returns = pd.Series([0.01, 0.02, 0.03])
    assert profit_factor(returns) == float("inf")


def test_profit_factor_no_gains_returns_zero():
    returns = pd.Series([-0.01, -0.02])
    assert profit_factor(returns) == 0.0


def test_profit_factor_positive():
    np.random.seed(0)
    returns = pd.Series(np.random.randn(100) * 0.01)
    pf = profit_factor(returns)
    assert pf >= 0


# ---------------------------------------------------------------------------
# compute_all
# ---------------------------------------------------------------------------


def test_compute_all_returns_dict():
    result = _make_result([0.001, 0.002, -0.001] * 84)
    metrics = compute_all(result)
    assert isinstance(metrics, dict)


def test_compute_all_has_required_keys():
    result = _make_result([0.001] * 50)
    metrics = compute_all(result)
    required_keys = {
        "total_return_pct",
        "cagr_pct",
        "sharpe_ratio",
        "max_drawdown_pct",
        "win_rate_pct",
        "profit_factor",
        "final_equity",
        "initial_cash",
        "n_bars",
        "symbol",
        "strategy",
        "mode",
    }
    assert required_keys.issubset(metrics.keys())


def test_compute_all_symbol_matches_config():
    result = _make_result([0.001] * 30)
    metrics = compute_all(result)
    assert metrics["symbol"] == "GC=F"
