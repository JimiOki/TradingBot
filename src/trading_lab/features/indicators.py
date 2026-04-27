"""Pure indicator functions for the trading-lab features layer.

All functions are pure: they take a pd.Series or pd.DataFrame as input and
return a pd.Series. No I/O, no network calls, no side effects.

NaN values at the start of each series (warm-up period) are expected and correct.
"""
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    """Simple Moving Average."""
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window}")
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    """Exponential Moving Average."""
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window}")
    return series.ewm(span=window, adjust=False).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """Relative Strength Index (0–100). Uses Wilder's smoothing (EMA alpha=1/window)."""
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window}")
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def macd(
    series: pd.Series,
    fast_window: int = 12,
    slow_window: int = 26,
    signal_window: int = 9,
) -> pd.DataFrame:
    """MACD line, signal line, and histogram."""
    fast_ema = ema(series, fast_window)
    slow_ema = ema(series, slow_window)
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal_window, adjust=False).mean()
    return pd.DataFrame(
        {
            "macd_line": macd_line,
            "signal_line": signal_line,
            "histogram": macd_line - signal_line,
        },
        index=series.index,
    )


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """Average True Range using Wilder's smoothing."""
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / window, adjust=False).mean()


def sma_gap_pct(fast: pd.Series, slow: pd.Series) -> pd.Series:
    """Percentage gap between fast and slow SMA. Positive = fast above slow."""
    return (fast - slow) / slow * 100


def rolling_atr_average(atr_series: pd.Series, window: int = 30) -> pd.Series:
    """Rolling average of ATR. Used to detect high-volatility conditions."""
    return atr_series.rolling(window=window, min_periods=window).mean()


def bollinger_bands(series: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    """Bollinger Bands: middle SMA, upper and lower bands.

    Args:
        series:  Price series (typically close).
        window:  Look-back window for the SMA and std (default 20).
        num_std: Number of standard deviations for the bands (default 2.0).

    Returns:
        DataFrame with columns: upper, middle, lower.
        Warm-up rows (index < window-1) contain NaN in all columns.
    """
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window}")
    middle = series.rolling(window=window, min_periods=window).mean()
    std = series.rolling(window=window, min_periods=window).std(ddof=0)
    upper = middle + num_std * std
    lower = middle - num_std * std
    return pd.DataFrame({"upper": upper, "middle": middle, "lower": lower}, index=series.index)


def donchian_channel(high: pd.Series, low: pd.Series, window: int = 20) -> pd.DataFrame:
    """Donchian Channel: N-period high, low, and mid.

    Args:
        high:   High price series.
        low:    Low price series.
        window: Look-back window (default 20).

    Returns:
        DataFrame with columns: upper, middle, lower.
        Warm-up rows (index < window-1) contain NaN in all columns.
        The upper is the rolling N-day high; lower is the rolling N-day low.
        Middle is (upper + lower) / 2.
    """
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window}")
    upper = high.rolling(window=window, min_periods=window).max()
    lower = low.rolling(window=window, min_periods=window).min()
    middle = (upper + lower) / 2
    return pd.DataFrame({"upper": upper, "middle": middle, "lower": lower}, index=high.index)
