"""Bollinger Band strategy — breakout or mean-reversion mode.

Bands:
  middle = SMA(window)
  upper  = middle + num_std * rolling_std
  lower  = middle - num_std * rolling_std

Breakout mode (mode="breakout", default):
  +1 when close > upper band  (momentum breakout above)
  -1 when close < lower band  (momentum breakdown below)

Mean-reversion mode (mode="reversion"):
  +1 when close < lower band  (oversold — expect bounce up)
  -1 when close > upper band  (overbought — expect reversion down)

The fast_sma and slow_sma required columns are populated with upper_band and
lower_band respectively.

signal_strength_pct = (close - middle) / middle * 100

Stop loss:  ATR(14) * atr_multiplier below/above entry
Take profit: stop_distance * risk_reward_ratio above/below entry
"""
import pandas as pd

from trading_lab.features.indicators import atr, bollinger_bands, rsi, rolling_atr_average
from trading_lab.strategies.base import Strategy
from trading_lab.strategies.quality import (
    compute_stop_loss,
    compute_take_profit,
    confidence_score,
    is_conflicting,
    is_high_volatility,
)

_VALID_MODES = {"breakout", "reversion"}


class BollingerStrategy(Strategy):
    """Bollinger Band strategy supporting breakout and mean-reversion modes."""

    def __init__(
        self,
        bb_window: int = 20,
        num_std: float = 2.0,
        mode: str = "breakout",
        rsi_window: int = 14,
        rsi_overbought: float = 70.0,
        rsi_oversold: float = 30.0,
        atr_window: int = 14,
        atr_multiplier: float = 1.5,
        risk_reward_ratio: float = 2.0,
    ) -> None:
        if bb_window < 1:
            raise ValueError("bb_window must be >= 1.")
        if mode not in _VALID_MODES:
            raise ValueError(f"mode must be one of {_VALID_MODES}, got '{mode}'.")
        self.bb_window = bb_window
        self.num_std = num_std
        self.mode = mode
        self.rsi_window = rsi_window
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.atr_window = atr_window
        self.atr_multiplier = atr_multiplier
        self.risk_reward_ratio = risk_reward_ratio

    def generate_signals(self, bars: pd.DataFrame) -> pd.DataFrame:
        """Generate signals with Bollinger Band logic and quality scores."""
        if "close" not in bars.columns:
            raise ValueError("Bars DataFrame must contain a 'close' column.")
        if not isinstance(bars.index, pd.DatetimeIndex):
            raise ValueError("Bars DataFrame must have a DatetimeIndex.")

        df = bars.copy()

        # --- Indicators ---
        bb = bollinger_bands(df["close"], window=self.bb_window, num_std=self.num_std)
        df["bb_upper"] = bb["upper"]
        df["bb_middle"] = bb["middle"]
        df["bb_lower"] = bb["lower"]

        # fast_sma / slow_sma slots are filled with upper and lower bands
        df["fast_sma"] = bb["upper"]
        df["slow_sma"] = bb["lower"]

        df["rsi"] = rsi(df["close"], self.rsi_window)
        df["atr_value"] = atr(df["high"], df["low"], df["close"], self.atr_window)
        df["rolling_avg_atr"] = rolling_atr_average(df["atr_value"], window=30)

        # --- Band signal ---
        above_upper = df["close"] > df["bb_upper"]
        below_lower = df["close"] < df["bb_lower"]

        raw_signal = pd.Series(0, index=df.index, dtype=int)
        if self.mode == "breakout":
            raw_signal[above_upper] = 1
            raw_signal[below_lower] = -1
        else:  # reversion
            raw_signal[below_lower] = 1
            raw_signal[above_upper] = -1

        # --- RSI filter ---
        filtered_signal = raw_signal.copy()
        long_but_overbought = (raw_signal == 1) & (df["rsi"] > self.rsi_overbought)
        short_but_oversold = (raw_signal == -1) & (df["rsi"] < self.rsi_oversold)
        filtered_signal[long_but_overbought] = 0
        filtered_signal[short_but_oversold] = 0

        df["signal"] = filtered_signal
        df["position_change"] = df["signal"].diff().fillna(0)

        # --- Signal strength ---
        df["signal_strength_pct"] = (df["close"] - df["bb_middle"]) / df["bb_middle"] * 100

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
