"""Donchian Channel Breakout strategy with RSI filter.

Signal logic:
- Long  (+1): close > N-day high (breakout above upper channel)
- Short (-1): close < N-day low  (breakdown below lower channel)
- Exit long : close < mid channel (average of upper and lower)
- Exit short: close > mid channel
- Flat   (0): close within channel, or exit condition overrides

The fast_sma and slow_sma required columns are populated with the upper and
lower Donchian channel levels respectively.

signal_strength_pct = (close - mid_channel) / mid_channel * 100

Stop loss:  ATR(14) * atr_multiplier below/above entry
Take profit: stop_distance * risk_reward_ratio above/below entry
"""
import pandas as pd

from trading_lab.features.indicators import atr, donchian_channel, rsi, rolling_atr_average, sma
from trading_lab.strategies.base import Strategy
from trading_lab.strategies.quality import (
    compute_stop_loss,
    compute_take_profit,
    confidence_score,
    is_conflicting,
    is_high_volatility,
)


class DonchianStrategy(Strategy):
    """Donchian Channel breakout strategy with RSI filter and full signal quality scoring."""

    def __init__(
        self,
        channel_window: int = 20,
        rsi_window: int = 14,
        rsi_overbought: float = 70.0,
        rsi_oversold: float = 30.0,
        atr_window: int = 14,
        atr_multiplier: float = 1.5,
        risk_reward_ratio: float = 2.0,
    ) -> None:
        if channel_window < 1:
            raise ValueError("channel_window must be >= 1.")
        self.channel_window = channel_window
        self.rsi_window = rsi_window
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.atr_window = atr_window
        self.atr_multiplier = atr_multiplier
        self.risk_reward_ratio = risk_reward_ratio

    def generate_signals(self, bars: pd.DataFrame) -> pd.DataFrame:
        """Generate signals with Donchian breakout logic and quality scores."""
        if "close" not in bars.columns:
            raise ValueError("Bars DataFrame must contain a 'close' column.")
        if not isinstance(bars.index, pd.DatetimeIndex):
            raise ValueError("Bars DataFrame must have a DatetimeIndex.")

        df = bars.copy()

        # --- Indicators ---
        dc = donchian_channel(df["high"], df["low"], self.channel_window)
        df["dc_upper"] = dc["upper"]
        df["dc_middle"] = dc["middle"]
        df["dc_lower"] = dc["lower"]

        # fast_sma / slow_sma slots are filled with the channel upper and lower
        df["fast_sma"] = dc["upper"]
        df["slow_sma"] = dc["lower"]

        df["rsi"] = rsi(df["close"], self.rsi_window)
        df["atr_value"] = atr(df["high"], df["low"], df["close"], self.atr_window)
        df["rolling_avg_atr"] = rolling_atr_average(df["atr_value"], window=30)

        # --- Breakout signal ---
        # Use the *previous* bar's channel to avoid look-ahead bias
        prev_upper = df["dc_upper"].shift(1)
        prev_lower = df["dc_lower"].shift(1)
        prev_middle = df["dc_middle"].shift(1)

        breakout_long = df["close"] > prev_upper
        breakout_short = df["close"] < prev_lower
        exit_long = df["close"] < prev_middle
        exit_short = df["close"] > prev_middle

        raw_signal = pd.Series(0, index=df.index, dtype=int)
        raw_signal[breakout_long] = 1
        raw_signal[breakout_short] = -1
        # Exit overrides: treat exit as flat (0) — already 0 by default
        # A breakout on the same bar takes priority over an exit check; the
        # conditions are mutually exclusive by construction (close can't be
        # both > upper and < middle simultaneously when upper > middle).

        # --- RSI filter: suppress signal if RSI contradicts direction ---
        filtered_signal = raw_signal.copy()
        long_but_overbought = (raw_signal == 1) & (df["rsi"] > self.rsi_overbought)
        short_but_oversold = (raw_signal == -1) & (df["rsi"] < self.rsi_oversold)
        filtered_signal[long_but_overbought] = 0
        filtered_signal[short_but_oversold] = 0

        df["signal"] = filtered_signal
        df["position_change"] = df["signal"].diff().fillna(0)

        # --- Signal strength ---
        df["signal_strength_pct"] = (df["close"] - df["dc_middle"]) / df["dc_middle"] * 100

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
            strength = row["signal_strength_pct"]

            stop = compute_stop_loss(sig, close, atr_val, self.atr_multiplier)
            stop_dist = abs(close - stop) if not pd.isna(stop) else float("nan")
            tp = compute_take_profit(sig, close, stop_dist, self.risk_reward_ratio)

            confidence_scores.append(confidence_score(sig, strength, rsi_val))
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
