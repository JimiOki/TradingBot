"""Backtest performance metrics.

All functions are pure: they take a BacktestResult or pd.Series and return
scalar values. No I/O, no side effects.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from trading_lab.backtesting.models import BacktestResult


def sharpe_ratio(net_returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Annualised Sharpe ratio (daily returns, 252 trading days).

    Args:
        net_returns:    Daily net return series.
        risk_free_rate: Annual risk-free rate (default 0.0).

    Returns:
        Annualised Sharpe ratio. Returns 0.0 if std is zero.
    """
    excess = net_returns - risk_free_rate / 252
    std = excess.std()
    if std == 0 or np.isnan(std):
        return 0.0
    return float((excess.mean() / std) * np.sqrt(252))


def max_drawdown(equity: pd.Series) -> float:
    """Maximum peak-to-trough drawdown as a percentage.

    Args:
        equity: Equity curve series.

    Returns:
        Max drawdown as a positive percentage (e.g. 15.3 means 15.3% drawdown).
    """
    peak = equity.cummax()
    drawdown = (equity - peak) / peak
    return float(abs(drawdown.min()) * 100)


def win_rate(net_returns: pd.Series, positions: pd.Series) -> float:
    """Percentage of trades that were profitable.

    A trade is defined as a period where position != 0.
    Only completed trades (position changes back to 0 or flips) are counted.

    Args:
        net_returns: Daily net return series.
        positions:   Position series (1, 0, -1).

    Returns:
        Win rate as a percentage (e.g. 55.0 means 55% of trades were profitable).
    """
    trade_returns = net_returns[positions != 0]
    if trade_returns.empty:
        return 0.0
    wins = (trade_returns > 0).sum()
    return float(wins / len(trade_returns) * 100)


def cagr(equity: pd.Series, periods_per_year: int = 252) -> float:
    """Compound Annual Growth Rate.

    Args:
        equity:           Equity curve series.
        periods_per_year: Number of bars per year (default 252 for daily).

    Returns:
        CAGR as a percentage (e.g. 18.5 means 18.5% per year).
    """
    if len(equity) < 2:
        return 0.0
    n_years = len(equity) / periods_per_year
    total_return = equity.iloc[-1] / equity.iloc[0]
    return float((total_return ** (1 / n_years) - 1) * 100)


def profit_factor(net_returns: pd.Series) -> float:
    """Ratio of gross profit to gross loss.

    Args:
        net_returns: Daily net return series.

    Returns:
        Profit factor. Returns float('inf') if there are no losing days.
        Returns 0.0 if there are no winning days.
    """
    gains = net_returns[net_returns > 0].sum()
    losses = abs(net_returns[net_returns < 0].sum())
    if losses == 0:
        return float("inf")
    if gains == 0:
        return 0.0
    return float(gains / losses)


def compute_all(result: BacktestResult) -> dict:
    """Compute the full metrics suite for a BacktestResult.

    Returns:
        Dictionary of metric name → value.
    """
    df = result.signals_df.dropna(subset=["equity", "net_return"])
    equity = df["equity"]
    net_returns = df["net_return"]
    positions = df["position"]

    return {
        "total_return_pct": result.total_return_pct,
        "cagr_pct": cagr(equity),
        "sharpe_ratio": sharpe_ratio(net_returns),
        "max_drawdown_pct": max_drawdown(equity),
        "win_rate_pct": win_rate(net_returns, positions),
        "profit_factor": profit_factor(net_returns),
        "final_equity": result.final_equity,
        "initial_cash": result.config.initial_cash,
        "n_bars": len(df),
        "symbol": result.config.symbol,
        "strategy": result.config.strategy_name,
        "mode": result.config.mode,
    }
