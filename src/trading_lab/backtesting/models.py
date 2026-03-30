from dataclasses import dataclass


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 100000.0
    commission_bps: float = 5.0
    slippage_bps: float = 2.0
