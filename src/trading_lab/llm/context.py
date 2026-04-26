"""SignalContext dataclass — structured input to the LLM layer."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class SignalContext:
    """All information needed to generate an LLM explanation or decision.

    REQ-LLM-002: SignalContext must be a frozen dataclass. All fields required.
    """
    symbol: str
    instrument_name: str
    signal_date: date
    signal: int                   # 1 (LONG) or -1 (SHORT)
    signal_direction: str         # "LONG" or "SHORT"
    close: float
    fast_sma: float
    slow_sma: float
    rsi: float
    recent_trend_summary: str     # e.g. "price up 4.2% over 5 bars"
    stop_loss_level: float
    take_profit_level: float
    risk_reward_ratio: float
    confidence_score: int
    conflicting_indicators: bool
    high_volatility: bool
    news_headlines: list[dict]    # each: {title, source, timestamp}; empty if none


def build_signal_context(
    signal_row: dict,
    instrument: dict,
    news: list[dict],
) -> SignalContext:
    """Build a SignalContext from a signal row dict and instrument config dict.

    Args:
        signal_row:  Dict with keys matching the signal schema columns.
        instrument:  Instrument config dict (from instruments.yaml).
        news:        List of news headline dicts [{title, source, timestamp}].

    Returns:
        Populated SignalContext ready for the LLM layer.
    """
    signal = int(signal_row["signal"])
    direction = "LONG" if signal == 1 else "SHORT"

    close = float(signal_row["close"])
    stop = float(signal_row.get("stop_loss_level") or 0.0)
    tp = float(signal_row.get("take_profit_level") or 0.0)

    stop_dist = abs(close - stop) if stop else 0.0
    rr = abs(tp - close) / stop_dist if stop_dist > 0 else 0.0

    # Build a short recent_trend_summary from close vs fast_sma
    fast_sma = float(signal_row.get("fast_sma") or close)
    pct = (close - fast_sma) / fast_sma * 100 if fast_sma else 0.0
    direction_word = "above" if pct >= 0 else "below"
    trend_summary = f"Close is {abs(pct):.1f}% {direction_word} fast SMA"

    return SignalContext(
        symbol=instrument.get("symbol", signal_row.get("symbol", "")),
        instrument_name=instrument.get("name", instrument.get("symbol", "")),
        signal_date=signal_row["signal_date"] if "signal_date" in signal_row else date.today(),
        signal=signal,
        signal_direction=direction,
        close=close,
        fast_sma=fast_sma,
        slow_sma=float(signal_row.get("slow_sma") or close),
        rsi=float(signal_row.get("rsi") or 50.0),
        recent_trend_summary=trend_summary,
        stop_loss_level=stop,
        take_profit_level=tp,
        risk_reward_ratio=round(rr, 2),
        confidence_score=int(signal_row.get("confidence_score") or 0),
        conflicting_indicators=bool(signal_row.get("conflicting_indicators", False)),
        high_volatility=bool(signal_row.get("high_volatility", False)),
        news_headlines=news or [],
    )
