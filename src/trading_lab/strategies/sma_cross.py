import pandas as pd

from trading_lab.strategies.base import Strategy


class SmaCrossStrategy(Strategy):
    def __init__(self, fast_window: int = 20, slow_window: int = 50) -> None:
        if fast_window >= slow_window:
            raise ValueError("fast_window must be smaller than slow_window.")
        self.fast_window = fast_window
        self.slow_window = slow_window

    def generate_signals(self, bars: pd.DataFrame) -> pd.DataFrame:
        required_columns = {"timestamp", "close"}
        missing = required_columns.difference(bars.columns)
        if missing:
            raise ValueError(f"Bars dataframe is missing columns: {sorted(missing)}")

        signals = bars.copy()
        signals["fast_sma"] = signals["close"].rolling(self.fast_window).mean()
        signals["slow_sma"] = signals["close"].rolling(self.slow_window).mean()
        signals["signal"] = 0
        signals.loc[signals["fast_sma"] > signals["slow_sma"], "signal"] = 1
        signals.loc[signals["fast_sma"] < signals["slow_sma"], "signal"] = -1
        signals["position_change"] = signals["signal"].diff().fillna(0)
        return signals
