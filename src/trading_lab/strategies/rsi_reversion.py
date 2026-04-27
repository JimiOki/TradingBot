"""RSI Mean Reversion strategy.

Signal logic (crossover — only fires on the bar RSI crosses the threshold):
- Long  (+1): RSI crosses *above* rsi_oversold from below
              (RSI was <= rsi_oversold on previous bar, now > rsi_oversold)
- Short (-1): RSI crosses *below* rsi_overbought from above
              (RSI was >= rsi_overbought on previous bar, now < rsi_overbought)
- Flat   (0): no crossover on this bar

SMA(20) and SMA(50) are computed and stored in the fast_sma / slow_sma
columns as required by the base class, but they do not influence the signal.

signal_strength_pct = distance of RSI from the threshold as a % of the threshold.
  Long  example: RSI=25, threshold=30 → (30-25)/30*100 = 16.67
  Short example: RSI=75, threshold=70 → (75-70)/70*100 = 7.14

Stop loss:  ATR(14) * atr_multiplier below/above entry
Take profit: stop_distance * risk_reward_ratio above/below entry
"""
import pandas as pd

from trading_lab.features.indicators import atr, rsi, rolling_atr_average, sma
from trading_lab.strategies.base import Strategy
from trading_lab.strategies.quality import (
    compute_stop_loss,
    compute_take_profit,
    confidence_score,
    is_conflicting,
    is_high_volatility,
)


class RsiReversionStrategy(Strategy):
    """RSI mean-reversion strategy using threshold crossovers."""

    def __init__(
        self,
        rsi_window: int = 14,
        rsi_overbought: float = 70.0,
        rsi_oversold: float = 30.0,
        fast_sma_window: int = 20,
        slow_sma_window: int = 50,
        atr_window: int = 14,
        atr_multiplier: float = 1.5,
        risk_reward_ratio: float = 2.0,
    ) -> None:
        if rsi_oversold >= rsi_overbought:
            raise ValueError("rsi_oversold must be less than rsi_overbought.")
        self.rsi_window = rsi_window
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.fast_sma_window = fast_sma_window
        self.slow_sma_window = slow_sma_window
        self.atr_window = atr_window
        self.atr_multiplier = atr_multiplier
        self.risk_reward_ratio = risk_reward_ratio

    def generate_signals(self, bars: pd.DataFrame) -> pd.DataFrame:
        """Generate signals based on RSI threshold crossovers."""
        if "close" not in bars.columns:
            raise ValueError("Bars DataFrame must contain a 'close' column.")
        if not isinstance(bars.index, pd.DatetimeIndex):
            raise ValueError("Bars DataFrame must have a DatetimeIndex.")

        df = bars.copy()

        # --- Indicators ---
        df["rsi"] = rsi(df["close"], self.rsi_window)
        df["fast_sma"] = sma(df["close"], self.fast_sma_window)
        df["slow_sma"] = sma(df["close"], self.slow_sma_window)
        df["atr_value"] = atr(df["high"], df["low"], df["close"], self.atr_window)
        df["rolling_avg_atr"] = rolling_atr_average(df["atr_value"], window=30)

        prev_rsi = df["rsi"].shift(1)

        # Long: RSI crosses above oversold threshold
        crosses_above_oversold = (prev_rsi <= self.rsi_oversold) & (df["rsi"] > self.rsi_oversold)
        # Short: RSI crosses below overbought threshold
        crosses_below_overbought = (prev_rsi >= self.rsi_overbought) & (df["rsi"] < self.rsi_overbought)

        raw_signal = pd.Series(0, index=df.index, dtype=int)
        raw_signal[crosses_above_oversold] = 1
        raw_signal[crosses_below_overbought] = -1

        df["signal"] = raw_signal
        df["position_change"] = df["signal"].diff().fillna(0)

        # --- Signal strength: distance of RSI from the threshold as % of threshold ---
        strength = pd.Series(0.0, index=df.index)
        long_mask = raw_signal == 1
        short_mask = raw_signal == -1
        strength[long_mask] = (
            (self.rsi_oversold - df.loc[long_mask, "rsi"]) / self.rsi_oversold * 100
        )
        strength[short_mask] = (
            (df.loc[short_mask, "rsi"] - self.rsi_overbought) / self.rsi_overbought * 100
        )
        df["signal_strength_pct"] = strength

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
            strength_val = row["signal_strength_pct"]

            stop = compute_stop_loss(sig, close, atr_val, self.atr_multiplier)
            stop_dist = abs(close - stop) if not pd.isna(stop) else float("nan")
            tp = compute_take_profit(sig, close, stop_dist, self.risk_reward_ratio)

            confidence_scores.append(confidence_score(sig, strength_val, rsi_val))
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
