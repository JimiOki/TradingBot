"""SMA Crossover strategy with RSI filter.

Signal logic:
- Long  (+1): fast SMA > slow SMA AND RSI not overbought (RSI <= rsi_overbought)
- Short (-1): fast SMA < slow SMA AND RSI not oversold  (RSI >= rsi_oversold)
- Flat   (0): SMAs equal, or RSI filter suppresses the signal

Stop loss:  ATR(14) * atr_multiplier below/above entry
Take profit: stop_distance * risk_reward_ratio above/below entry
"""
import pandas as pd

from trading_lab.features.indicators import atr, rsi, rolling_atr_average, sma, sma_gap_pct
from trading_lab.strategies.base import Strategy
from trading_lab.strategies.quality import (
    compute_stop_loss,
    compute_take_profit,
    confidence_score,
    is_conflicting,
    is_high_volatility,
    signal_strength_pct,
)


class SmaCrossStrategy(Strategy):
    """SMA crossover strategy with RSI filter and full signal quality scoring."""

    def __init__(
        self,
        fast_window: int = 20,
        slow_window: int = 50,
        rsi_window: int = 14,
        rsi_overbought: float = 70.0,
        rsi_oversold: float = 30.0,
        atr_window: int = 14,
        atr_multiplier: float = 1.5,
        risk_reward_ratio: float = 2.0,
    ) -> None:
        if fast_window >= slow_window:
            raise ValueError("fast_window must be smaller than slow_window.")
        self.fast_window = fast_window
        self.slow_window = slow_window
        self.rsi_window = rsi_window
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.atr_window = atr_window
        self.atr_multiplier = atr_multiplier
        self.risk_reward_ratio = risk_reward_ratio

    def generate_signals(self, bars: pd.DataFrame) -> pd.DataFrame:
        """Generate signals with RSI filter, stop/target levels, and quality scores."""
        if "close" not in bars.columns:
            raise ValueError("Bars DataFrame must contain a 'close' column.")
        if not isinstance(bars.index, pd.DatetimeIndex):
            raise ValueError("Bars DataFrame must have a DatetimeIndex.")

        df = bars.copy()

        # --- Indicators ---
        df["fast_sma"] = sma(df["close"], self.fast_window)
        df["slow_sma"] = sma(df["close"], self.slow_window)
        df["rsi"] = rsi(df["close"], self.rsi_window)
        df["atr_value"] = atr(df["high"], df["low"], df["close"], self.atr_window)
        df["rolling_avg_atr"] = rolling_atr_average(df["atr_value"], window=30)

        # --- Raw crossover signal ---
        raw_signal = pd.Series(0, index=df.index, dtype=int)
        raw_signal[df["fast_sma"] > df["slow_sma"]] = 1
        raw_signal[df["fast_sma"] < df["slow_sma"]] = -1

        # --- RSI filter: suppress signal if RSI contradicts direction ---
        filtered_signal = raw_signal.copy()
        long_but_overbought = (raw_signal == 1) & (df["rsi"] > self.rsi_overbought)
        short_but_oversold = (raw_signal == -1) & (df["rsi"] < self.rsi_oversold)
        filtered_signal[long_but_overbought] = 0
        filtered_signal[short_but_oversold] = 0

        df["signal"] = filtered_signal
        df["position_change"] = df["signal"].diff().fillna(0)

        # --- Signal strength ---
        df["signal_strength_pct"] = sma_gap_pct(df["fast_sma"], df["slow_sma"])

        # --- Row-wise quality and stop/target ---
        confidence_scores = []
        conflicting_flags = []
        high_vol_flags = []
        stop_levels = []
        take_profits = []
        stop_distances = []

        for _, row in df.iterrows():
            sig = int(row["signal"])
            rsi_val = row["rsi"]
            close = row["close"]
            atr_val = row["atr_value"]
            rolling_atr = row["rolling_avg_atr"]
            gap_pct = row["signal_strength_pct"]

            stop = compute_stop_loss(sig, close, atr_val, self.atr_multiplier)
            stop_dist = abs(close - stop) if not pd.isna(stop) else float("nan")
            tp = compute_take_profit(sig, close, stop_dist, self.risk_reward_ratio)

            confidence_scores.append(confidence_score(sig, gap_pct, rsi_val))
            conflicting_flags.append(is_conflicting(sig, rsi_val))
            high_vol_flags.append(is_high_volatility(atr_val, rolling_atr))
            stop_levels.append(stop)
            stop_distances.append(stop_dist)
            take_profits.append(tp)

        df["confidence_score"] = confidence_scores
        df["conflicting_indicators"] = conflicting_flags
        df["high_volatility"] = high_vol_flags
        df["stop_loss_level"] = stop_levels
        df["stop_distance"] = stop_distances
        df["take_profit_level"] = take_profits

        return self._validate_output(df)
