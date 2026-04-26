"""Signal quality scoring functions.

All functions are pure: they operate on scalar values or pd.Series
and return computed quality metrics. No I/O, no side effects.
"""
import pandas as pd


def confidence_score(
    signal: int,
    sma_gap_pct: float,
    rsi_value: float,
) -> int:
    """Compute a 0-100 confidence score for a signal.

    Scoring:
    - Base score: 50
    - SMA gap bonus: +25 if abs(sma_gap_pct) > 1.0 (strong trend separation)
    - RSI direction bonus: +25 if RSI confirms signal direction
      (RSI < 40 confirms long, RSI > 60 confirms short)

    Args:
        signal:      Signal value: 1 (long), -1 (short), 0 (flat).
        sma_gap_pct: SMA gap as percentage of price (positive = fast above slow).
        rsi_value:   Current RSI value (0-100).

    Returns:
        Integer score 0-100. Returns 0 for flat signals.
    """
    if signal == 0:
        return 0

    score = 50

    if abs(sma_gap_pct) > 1.0:
        score += 25

    if signal == 1 and rsi_value < 40:
        score += 25
    elif signal == -1 and rsi_value > 60:
        score += 25

    return min(score, 100)


def signal_strength_pct(fast_sma: float, slow_sma: float) -> float:
    """SMA gap as a percentage of the slow SMA.

    Positive = fast above slow (bullish), negative = fast below slow (bearish).

    Args:
        fast_sma: Fast SMA value.
        slow_sma: Slow SMA value.

    Returns:
        Gap percentage. Returns 0.0 if slow_sma is zero.
    """
    if slow_sma == 0:
        return 0.0
    return (fast_sma - slow_sma) / slow_sma * 100


def is_conflicting(signal: int, rsi_value: float) -> bool:
    """Detect when SMA signal and RSI point in opposite directions.

    Conflict conditions:
    - Long signal but RSI > 70 (overbought — momentum may not support entry)
    - Short signal but RSI < 30 (oversold — momentum may not support entry)

    Args:
        signal:    Signal value: 1, -1, or 0.
        rsi_value: Current RSI value (0-100).

    Returns:
        True if a conflict is detected, False otherwise.
    """
    if signal == 1 and rsi_value > 70:
        return True
    if signal == -1 and rsi_value < 30:
        return True
    return False


def is_high_volatility(current_atr: float, rolling_avg_atr: float) -> bool:
    """Flag high-volatility conditions.

    A signal is flagged HIGH VOLATILITY when current ATR exceeds 2x
    its 30-day rolling average.

    Args:
        current_atr:     Current ATR(14) value.
        rolling_avg_atr: 30-day rolling average of ATR(14).

    Returns:
        True if high volatility is detected. False if rolling_avg_atr is NaN or zero.
    """
    if pd.isna(rolling_avg_atr) or rolling_avg_atr == 0:
        return False
    return current_atr > 2 * rolling_avg_atr


def compute_stop_loss(
    signal: int,
    close: float,
    atr_value: float,
    atr_multiplier: float = 1.5,
) -> float:
    """Compute ATR-based stop loss level.

    Stop distance = atr_multiplier * ATR(14)
    Long:  stop = close - stop_distance
    Short: stop = close + stop_distance

    Args:
        signal:         Signal direction: 1 (long), -1 (short), 0 (flat).
        close:          Entry price (current close).
        atr_value:      Current ATR(14) value.
        atr_multiplier: Multiplier applied to ATR (default 1.5, configurable).

    Returns:
        Stop loss price level. Returns float('nan') for flat signals.
    """
    if signal == 0 or pd.isna(atr_value):
        return float("nan")
    stop_distance = atr_multiplier * atr_value
    if signal == 1:
        return close - stop_distance
    return close + stop_distance


def compute_take_profit(
    signal: int,
    close: float,
    stop_distance: float,
    risk_reward_ratio: float = 2.0,
) -> float:
    """Compute take profit level based on risk/reward ratio.

    Target distance = stop_distance * risk_reward_ratio
    Long:  target = close + target_distance
    Short: target = close - target_distance

    Args:
        signal:            Signal direction: 1, -1, or 0.
        close:             Entry price.
        stop_distance:     Absolute distance from entry to stop.
        risk_reward_ratio: Reward multiple of risk (default 2.0 = 2:1 R/R).

    Returns:
        Take profit price level. Returns float('nan') for flat signals.
    """
    if signal == 0 or pd.isna(stop_distance):
        return float("nan")
    target_distance = stop_distance * risk_reward_ratio
    if signal == 1:
        return close + target_distance
    return close - target_distance
