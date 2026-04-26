"""Abstract base class for all trading strategies.

All strategies must:
- Accept a curated bars DataFrame with a DatetimeIndex (UTC)
- Return a signals DataFrame with all required columns populated
- Never perform I/O, network calls, or broker interactions
"""
from abc import ABC, abstractmethod

import pandas as pd

# Required columns in every signals DataFrame returned by a strategy
REQUIRED_SIGNAL_COLUMNS = {
    "close",
    "signal",
    "position_change",
    "fast_sma",
    "slow_sma",
    "rsi",
    "stop_loss_level",
    "take_profit_level",
    "stop_distance",
    "atr_value",
    "confidence_score",
    "signal_strength_pct",
    "conflicting_indicators",
    "high_volatility",
}

VALID_SIGNAL_VALUES = {-1, 0, 1}


class Strategy(ABC):
    """Abstract base class for all trading strategies."""

    @abstractmethod
    def generate_signals(self, bars: pd.DataFrame) -> pd.DataFrame:
        """Generate trading signals from a curated bars DataFrame.

        Args:
            bars: Curated DataFrame with DatetimeIndex (UTC) and OHLCV columns.

        Returns:
            Signals DataFrame with all REQUIRED_SIGNAL_COLUMNS populated.
        """

    def _validate_output(self, signals: pd.DataFrame) -> pd.DataFrame:
        """Validate that the signals DataFrame meets the contract.

        Call this at the end of generate_signals() before returning.

        Raises:
            ValueError: If required columns are missing or signal values are invalid.
        """
        missing = REQUIRED_SIGNAL_COLUMNS - set(signals.columns)
        if missing:
            raise ValueError(
                f"{self.__class__.__name__} is missing required signal columns: {sorted(missing)}"
            )

        invalid = signals["signal"].dropna()
        invalid = invalid[~invalid.isin(VALID_SIGNAL_VALUES)]
        if not invalid.empty:
            raise ValueError(
                f"{self.__class__.__name__} produced invalid signal values: {invalid.unique().tolist()}"
            )

        return signals
