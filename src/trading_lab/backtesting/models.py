"""Data models for the backtesting layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import pandas as pd


@dataclass
class BacktestConfig:
    """Full specification for a backtest run.

    All fields must be set explicitly so that a result can be reproduced
    from the config alone.
    """
    # Identity
    symbol: str
    strategy_name: str
    timeframe: str = "1d"

    # Date range
    start_date: date | None = None
    end_date: date | None = None

    # Capital and costs
    initial_cash: float = 100_000.0
    commission_bps: float = 5.0
    slippage_bps: float = 2.0

    # Strategy parameters — stored for reproducibility
    strategy_params: dict = field(default_factory=dict)

    # Validation mode
    mode: Literal["full", "in_sample", "out_of_sample"] = "full"
    oos_ratio: float = 0.3
    parameters_locked: bool = False


@dataclass
class BacktestResult:
    """Output of a completed backtest run."""
    signals_df: pd.DataFrame
    config: BacktestConfig

    @property
    def final_equity(self) -> float:
        return self.signals_df["equity"].iloc[-1]

    @property
    def total_return_pct(self) -> float:
        return (self.final_equity / self.config.initial_cash - 1) * 100
