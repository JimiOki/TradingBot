"""In-sample / out-of-sample validation framework.

Prevents overfitting by enforcing a strict split between the data used to
tune strategy parameters and the data used to evaluate them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from trading_lab.backtesting.models import BacktestResult


class ValidationOrderError(Exception):
    """Raised when out-of-sample evaluation is attempted before parameters are locked."""


class ParameterDriftError(Exception):
    """Raised when strategy parameters change after the in-sample run is complete."""


@dataclass(frozen=True)
class ValidationResult:
    """Result of out-of-sample threshold validation."""
    approved: bool
    sharpe_ratio: float
    max_drawdown_pct: float
    reason: str
    overfitting_warning: bool = False
    degradation_pct: float | None = None


def split_in_sample_out_of_sample(
    bars_df: pd.DataFrame,
    oos_ratio: float = 0.3,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split bars chronologically into in-sample and out-of-sample sets.

    The split is always chronological — the most recent data is held out.
    This prevents any form of future data leakage.

    Args:
        bars_df:   Curated bars DataFrame with DatetimeIndex.
        oos_ratio: Fraction of data to hold out for out-of-sample (default 0.3).

    Returns:
        Tuple of (in_sample_df, out_of_sample_df).

    Raises:
        ValueError: If oos_ratio is invalid or bars_df has fewer than 30 bars.
    """
    if not 0 < oos_ratio < 1:
        raise ValueError(f"oos_ratio must be between 0 and 1, got {oos_ratio}")
    if len(bars_df) < 30:
        raise ValueError(
            f"bars_df must have at least 30 bars for a meaningful split, got {len(bars_df)}"
        )

    split_idx = int(len(bars_df) * (1 - oos_ratio))
    split_idx = max(split_idx, 1)

    in_sample = bars_df.iloc[:split_idx].copy()
    out_of_sample = bars_df.iloc[split_idx:].copy()

    return in_sample, out_of_sample


def validate_oos_thresholds(
    result: BacktestResult,
    min_sharpe: float = 0.5,
    max_drawdown_pct: float = 25.0,
) -> ValidationResult:
    """Evaluate whether an out-of-sample backtest meets approval thresholds.

    A strategy must pass these thresholds before paper trading is permitted.

    Args:
        result:           BacktestResult from an out-of-sample backtest run.
        min_sharpe:       Minimum acceptable Sharpe ratio (default 0.5).
        max_drawdown_pct: Maximum acceptable drawdown percentage (default 25.0).

    Returns:
        ValidationResult with approved flag and reason.
    """
    from trading_lab.backtesting.metrics import max_drawdown, sharpe_ratio

    df = result.signals_df.dropna(subset=["equity", "net_return"])
    sr = sharpe_ratio(df["net_return"])
    dd = max_drawdown(df["equity"])

    if sr < min_sharpe and dd > max_drawdown_pct:
        reason = f"Sharpe {sr:.2f} < {min_sharpe} AND drawdown {dd:.1f}% > {max_drawdown_pct}%"
        approved = False
    elif sr < min_sharpe:
        reason = f"Sharpe ratio {sr:.2f} is below minimum {min_sharpe}"
        approved = False
    elif dd > max_drawdown_pct:
        reason = f"Max drawdown {dd:.1f}% exceeds maximum {max_drawdown_pct}%"
        approved = False
    else:
        reason = f"Sharpe {sr:.2f} >= {min_sharpe} AND drawdown {dd:.1f}% <= {max_drawdown_pct}%"
        approved = True

    return ValidationResult(
        approved=approved,
        sharpe_ratio=sr,
        max_drawdown_pct=dd,
        reason=reason,
    )


def compute_performance_degradation(
    in_sample_result: BacktestResult,
    oos_result: BacktestResult,
) -> float | None:
    """Compute performance degradation between in-sample and out-of-sample.

    Degradation = (in_sample_sharpe - oos_sharpe) / in_sample_sharpe * 100

    If degradation > 50%, an overfitting warning should be displayed.

    Args:
        in_sample_result: BacktestResult from in-sample period.
        oos_result:       BacktestResult from out-of-sample period.

    Returns:
        Degradation as a percentage, or None if in-sample Sharpe <= 0.
    """
    from trading_lab.backtesting.metrics import sharpe_ratio

    is_df = in_sample_result.signals_df.dropna(subset=["net_return"])
    oos_df = oos_result.signals_df.dropna(subset=["net_return"])

    is_sharpe = sharpe_ratio(is_df["net_return"])
    oos_sharpe = sharpe_ratio(oos_df["net_return"])

    if is_sharpe <= 0:
        return None

    return (is_sharpe - oos_sharpe) / is_sharpe * 100
