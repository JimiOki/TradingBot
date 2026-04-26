"""Tests for src/trading_lab/backtesting/validation.py"""
import numpy as np
import pandas as pd
import pytest

from trading_lab.backtesting.models import BacktestConfig, BacktestResult
from trading_lab.backtesting.validation import (
    compute_performance_degradation,
    split_in_sample_out_of_sample,
    validate_oos_thresholds,
)


def _config(**kwargs) -> BacktestConfig:
    defaults = dict(symbol="GC=F", strategy_name="test", initial_cash=100_000.0)
    defaults.update(kwargs)
    return BacktestConfig(**defaults)


def _make_bars(n: int = 100) -> pd.DataFrame:
    dates = pd.date_range("2023-01-01", periods=n, freq="B", tz="UTC")
    close = 100.0 + np.arange(n, dtype=float)
    return pd.DataFrame({"close": close}, index=dates)


def _make_result(net_returns: list[float]) -> BacktestResult:
    n = len(net_returns)
    dates = pd.date_range("2023-01-01", periods=n, freq="B", tz="UTC")
    nr = pd.Series(net_returns, index=dates)
    equity = 100_000.0 * (1 + nr).cumprod()
    df = pd.DataFrame(
        {"net_return": nr, "equity": equity, "position": 1},
        index=dates,
    )
    return BacktestResult(signals_df=df, config=_config())


# ---------------------------------------------------------------------------
# split_in_sample_out_of_sample
# ---------------------------------------------------------------------------


def test_split_default_ratio_30pct_oos():
    bars = _make_bars(100)
    is_df, oos_df = split_in_sample_out_of_sample(bars, oos_ratio=0.3)
    assert len(is_df) == 70
    assert len(oos_df) == 30


def test_split_total_length_preserved():
    bars = _make_bars(100)
    is_df, oos_df = split_in_sample_out_of_sample(bars)
    assert len(is_df) + len(oos_df) == 100


def test_split_is_chronological():
    bars = _make_bars(100)
    is_df, oos_df = split_in_sample_out_of_sample(bars)
    assert is_df.index[-1] < oos_df.index[0]


def test_split_no_overlap():
    bars = _make_bars(100)
    is_df, oos_df = split_in_sample_out_of_sample(bars)
    overlap = is_df.index.intersection(oos_df.index)
    assert len(overlap) == 0


def test_split_invalid_ratio_zero_raises():
    with pytest.raises(ValueError):
        split_in_sample_out_of_sample(_make_bars(100), oos_ratio=0.0)


def test_split_invalid_ratio_one_raises():
    with pytest.raises(ValueError):
        split_in_sample_out_of_sample(_make_bars(100), oos_ratio=1.0)


def test_split_invalid_ratio_negative_raises():
    with pytest.raises(ValueError):
        split_in_sample_out_of_sample(_make_bars(100), oos_ratio=-0.1)


def test_split_too_few_bars_raises():
    with pytest.raises(ValueError):
        split_in_sample_out_of_sample(_make_bars(29))


def test_split_exactly_30_bars_succeeds():
    bars = _make_bars(30)
    is_df, oos_df = split_in_sample_out_of_sample(bars)
    assert len(is_df) + len(oos_df) == 30


# ---------------------------------------------------------------------------
# validate_oos_thresholds
# ---------------------------------------------------------------------------


def test_validation_passes_good_result():
    """High Sharpe, low drawdown → approved."""
    # Alternating returns give non-zero std → computable Sharpe
    result = _make_result([0.005, 0.006] * 126)
    vr = validate_oos_thresholds(result, min_sharpe=0.5, max_drawdown_pct=25.0)
    assert vr.approved is True


def test_validation_fails_low_sharpe():
    # Flat returns → Sharpe = 0
    result = _make_result([0.0] * 100)
    vr = validate_oos_thresholds(result, min_sharpe=0.5, max_drawdown_pct=25.0)
    assert vr.approved is False
    assert "Sharpe" in vr.reason


def test_validation_fails_high_drawdown():
    # Returns that create a deep drawdown
    returns = [0.01] * 50 + [-0.015] * 50  # peak then sharp decline
    result = _make_result(returns)
    vr = validate_oos_thresholds(result, min_sharpe=0.0, max_drawdown_pct=5.0)
    assert vr.approved is False
    assert "drawdown" in vr.reason.lower()


def test_validation_result_has_sharpe_and_drawdown():
    result = _make_result([0.001] * 100)
    vr = validate_oos_thresholds(result)
    assert isinstance(vr.sharpe_ratio, float)
    assert isinstance(vr.max_drawdown_pct, float)


def test_validation_reason_is_string():
    result = _make_result([0.001] * 100)
    vr = validate_oos_thresholds(result)
    assert isinstance(vr.reason, str) and len(vr.reason) > 0


# ---------------------------------------------------------------------------
# compute_performance_degradation
# ---------------------------------------------------------------------------


def test_degradation_none_when_is_sharpe_nonpositive():
    """If IS Sharpe <= 0, degradation is undefined → None."""
    flat_result = _make_result([0.0] * 100)
    oos_result = _make_result([0.001] * 100)
    assert compute_performance_degradation(flat_result, oos_result) is None


def test_degradation_zero_when_sharpes_equal():
    # Non-constant returns so std > 0 and sharpe is computable
    returns = [0.002, 0.004] * 126
    is_result = _make_result(returns)
    oos_result = _make_result(returns)
    degradation = compute_performance_degradation(is_result, oos_result)
    assert degradation is not None
    assert abs(degradation) < 1e-6


def test_degradation_positive_when_oos_worse():
    """OOS Sharpe lower than IS → positive degradation."""
    is_result = _make_result([0.005, 0.006] * 126)  # high, varying
    oos_result = _make_result([0.001, 0.002] * 126)  # low, varying
    degradation = compute_performance_degradation(is_result, oos_result)
    assert degradation is not None
    assert degradation > 0


def test_degradation_negative_when_oos_better():
    """OOS Sharpe higher than IS → negative degradation (performance improved)."""
    is_result = _make_result([0.001, 0.002] * 126)  # low, varying
    oos_result = _make_result([0.005, 0.006] * 126)  # high, varying
    degradation = compute_performance_degradation(is_result, oos_result)
    assert degradation is not None
    assert degradation < 0
