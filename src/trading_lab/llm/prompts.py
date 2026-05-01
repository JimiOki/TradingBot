"""Prompt templates for the LLM explanation and decision layers.

All templates are module-level string constants. They are not embedded in classes.
Both explanation prompts instruct the LLM to:
  - Write 3-5 sentences in plain English
  - Not make price predictions or give investment advice
  - Be directionally consistent with the signal
"""

EXPLANATION_PROMPT_WITH_NEWS = """\
You are a senior trader reviewing a signal for {instrument_name} ({symbol}). \
Your job is to critically assess whether the technical signal is supported or undermined \
by current market conditions and news. Be direct and opinionated — this is for a \
professional trader who needs your honest view, not a disclaimer.

## Technical Signal
- Signal Date: {signal_date}
- Direction: {signal_direction}
- Close Price: {close:.4f}
- Fast SMA ({fast_sma_period}): {fast_sma:.4f}
- Slow SMA ({slow_sma_period}): {slow_sma:.4f}
- RSI (14): {rsi:.1f}
- Recent Trend: {recent_trend_summary}
- Stop Loss: {stop_loss_level:.4f} | Take Profit: {take_profit_level:.4f} | R/R: {risk_reward_ratio:.1f}x
- Confidence: {confidence_score}/100 | Conflicting Indicators: {conflicting_indicators} | High Volatility: {high_volatility}

{strategy_signals_section}

## Key Price Levels
{sr_section}

## Volume
{volume_section}

## News & Sentiment
{news_section}

## Your Analysis (3-5 sentences)
1. What is the technical picture telling you — why is this signal {signal_direction} and how \
   strong is the conviction given the strategy consensus?
2. What specific market-moving information or risk factor does the news identify for \
   {instrument_name}? Extract the key macro or fundamental driver, not just the headline.
3. Does the news reinforce or challenge the technical signal? If they conflict, \
   say so explicitly and explain which carries more weight right now and why.
"""

EXPLANATION_PROMPT_NO_NEWS = """\
You are a senior trader reviewing a signal for {instrument_name} ({symbol}). \
Your job is to critically assess the technical signal and give an honest view \
on its strength and reliability. Be direct — this is for a professional trader.

## Technical Signal
- Signal Date: {signal_date}
- Direction: {signal_direction}
- Close Price: {close:.4f}
- Fast SMA ({fast_sma_period}): {fast_sma:.4f}
- Slow SMA ({slow_sma_period}): {slow_sma:.4f}
- RSI (14): {rsi:.1f}
- Recent Trend: {recent_trend_summary}
- Stop Loss: {stop_loss_level:.4f} | Take Profit: {take_profit_level:.4f} | R/R: {risk_reward_ratio:.1f}x
- Confidence: {confidence_score}/100 | Conflicting Indicators: {conflicting_indicators} | High Volatility: {high_volatility}

{strategy_signals_section}

## Key Price Levels
{sr_section}

## Volume
{volume_section}

## Your Analysis (3-4 sentences)
Explain what the technical picture is saying, how strong the conviction is given \
the strategy consensus, and what the main risk to this signal is.
"""

DECISION_PROMPT = """\
You are a discretionary spread-betting trader making a trading decision for {instrument_name} ({symbol}). \
You have been given technical evidence, news, and market sentiment. Your job is to weigh \
all of it, reach a conviction, and specify the trade parameters if acting.

## Technical Evidence
- Date: {signal_date}
- Close: {close:.4f} | Fast SMA: {fast_sma:.4f} | Slow SMA: {slow_sma:.4f}
- RSI (14): {rsi:.1f} | Trend: {recent_trend_summary}
- Suggested Stop: {stop_loss_level:.4f} | Suggested Target: {take_profit_level:.4f} | R/R: {risk_reward_ratio:.1f}x
- Conflicting Indicators: {conflicting_indicators} | High Volatility: {high_volatility}

{strategy_signals_section}

## Key Price Levels
{sr_section}

## Volume
{volume_section}
{news_section}

## How to reason
- Weigh the technical consensus, news catalysts, and sentiment together — no single input wins automatically
- A strong macro catalyst in the news can justify a direction that conflicts with weak technicals, and vice versa
- If IG client sentiment strongly opposes your intended direction (>70% on the other side), note it — \
  it may be a contrarian signal or a warning
- UNCERTAIN should only be used when evidence genuinely pulls equally in both directions — be decisive
- Set stop_loss at a level that invalidates your thesis — use the suggested stop as a reference but adjust \
  based on key technical levels (support/resistance, SMA lines, recent swing highs/lows)
- Set take_profit at a realistic target — the suggested target is a starting point
- Set risk_pct between 0.5 and 3.0 based on your conviction: low conviction = 0.5-1.0, \
  moderate = 1.0-2.0, high conviction = 2.0-3.0

## Timing & regime awareness
- If price is at or near all-time highs, extended far above SMAs, or RSI > 70, consider whether NOW \
  is the right entry or whether a pullback would offer better risk/reward
- In strong trends (price well above both SMAs, clear momentum), don't fight the trend with mean \
  reversion shorts — RSI can stay "overbought" for weeks in trending markets
- If you want to go with the trend but price is extended, set order_type to "LIMIT" and entry_level \
  to a pullback level (e.g. near fast SMA or recent support)
- If entry is attractive right now (price near support, consolidation, or fresh breakout with volume), \
  use order_type "MARKET"

Respond ONLY with a JSON object. No text outside the JSON.

Required format:
{{
  "recommendation": "GO" | "NO_GO" | "UNCERTAIN",
  "direction": "LONG" | "SHORT" | null,
  "order_type": "MARKET" | "LIMIT",
  "entry_level": <float or null>,
  "stop_loss": <float or null>,
  "take_profit": <float or null>,
  "risk_pct": <float or null>,
  "rationale": "2-3 sentences covering the key technical picture, the most relevant news or sentiment factor, and why you landed here",
  "conflicts_with_technical": true | false
}}

When recommendation is GO: direction, order_type, entry_level, stop_loss, take_profit, and risk_pct must all be set.
For MARKET orders, entry_level is the current close price (reference only).
For LIMIT orders, entry_level is the desired pullback entry price — must be below close for LONG, above close for SHORT.
When recommendation is NO_GO or UNCERTAIN: direction, entry_level, stop_loss, take_profit, and risk_pct must be null.
conflicts_with_technical should be true ONLY when the technical consensus has a clear directional signal (majority of strategies agree on LONG or SHORT) and your direction opposes it. When the technical consensus is neutral/flat, set this to false — choosing a direction when technicals are inconclusive is not a conflict.
"""


POSITION_MANAGEMENT_PROMPT = """\
You are a discretionary spread-betting trader managing an existing position on {instrument_name} ({symbol}).

## Your Open Position
- Direction: {position_direction}
- Entry Price: {entry_level:.4f}
- Current Price: {close:.4f}
- Unrealised P&L: {pnl_points:+.1f} points ({pnl_direction})
- Current Stop: {current_stop:.4f}
- Current Target: {current_target:.4f}

## Technical Evidence
- Date: {signal_date}
- Fast SMA: {fast_sma:.4f} | Slow SMA: {slow_sma:.4f}
- RSI (14): {rsi:.1f} | Trend: {recent_trend_summary}
- Conflicting Indicators: {conflicting_indicators} | High Volatility: {high_volatility}

{strategy_signals_section}

## Key Price Levels
{sr_section}
{news_section}

## How to reason
- You already have a position. The question is NOT whether to open a new trade — it's whether to HOLD, ADJUST, or CLOSE the existing one.
- HOLD: the trade thesis is still valid, no changes needed
- ADJUST: the trade thesis is still valid but stop or target should be updated based on new price action
  - Stops should generally move in the profitable direction (trailing stop) — tightening to lock in gains
  - For LONG positions: new stop must be >= current stop (never widen a losing stop)
  - For SHORT positions: new stop must be <= current stop (never widen a losing stop)
  - Targets can move in either direction (take profit early or extend a runner)
- CLOSE: the original thesis has been invalidated — close the position now
  - Close if the trend has reversed, key support/resistance has broken, or a major news event changes the outlook
  - Close if most strategies have flipped against your direction

Respond ONLY with a JSON object. No text outside the JSON.

Required format:
{{{{
  "recommendation": "HOLD" | "ADJUST" | "CLOSE",
  "stop_loss": <float or null>,
  "take_profit": <float or null>,
  "rationale": "2-3 sentences explaining your decision"
}}}}

When recommendation is HOLD: stop_loss and take_profit should be null (keep current levels).
When recommendation is ADJUST: stop_loss and/or take_profit should be the NEW levels. Only include the one(s) you want to change.
When recommendation is CLOSE: stop_loss and take_profit should be null.
"""


def _format_sr_section(context: "SignalContext") -> str:
    """Format support/resistance levels for the prompt."""
    lines = []
    if context.resistance_levels:
        res = [f"{r:.4f}" for r in context.resistance_levels[:3]]
        lines.append(f"- Resistance (swing highs above): {', '.join(res)}")
    if context.support_levels:
        sup = [f"{s:.4f}" for s in context.support_levels[:3]]
        lines.append(f"- Support (swing lows below): {', '.join(sup)}")
    if not lines:
        return "No recent swing levels identified."
    return "\n".join(lines)


def _format_volume_section(context: "SignalContext") -> str:
    """Format volume context for the prompt."""
    if context.volume_ratio is None:
        return "Volume data not available."
    ratio = context.volume_ratio
    if ratio > 1.5:
        desc = "significantly above average"
    elif ratio > 1.1:
        desc = "above average"
    elif ratio > 0.9:
        desc = "near average"
    elif ratio > 0.5:
        desc = "below average"
    else:
        desc = "very low"
    return f"- Current volume: {ratio:.1f}x 20-day average ({desc})"


def _format_news_section(headlines: list[dict]) -> str:
    """Format a list of news headline dicts into a readable string.

    Includes article body text where available so the LLM can read beyond
    the headline.
    """
    if not headlines:
        return "No recent news available."
    lines = []
    for h in headlines:
        ts = h.get("timestamp", "")
        title = h.get("title", "")
        source = h.get("source", "")
        body = h.get("body", "").strip()
        line = f"- [{ts}] {title} ({source})"
        if body:
            line += f"\n  {body}"
        lines.append(line)
    return "\n".join(lines)


def _format_strategy_signals(strategy_signals: dict) -> str:
    """Format a strategy signals dict into a readable section string.

    Args:
        strategy_signals: Dict mapping strategy name to signal int (-1, 0, 1).
                          Expected keys include: sma_cross, macd_cross, bollinger_breakout,
                          bollinger_reversion, donchian, rsi_reversion.

    Returns:
        A formatted string ready to embed in a prompt, or empty string if no signals.
    """
    if not strategy_signals:
        return ""

    _SIGNAL_LABEL = {1: "LONG", -1: "SHORT", 0: "NEUTRAL"}
    _KEY_TO_DISPLAY = {
        "sma_cross": "EMA Crossover",
        "macd_cross": "MACD Crossover",
        "bollinger_breakout": "Bollinger Band Breakout",
        "bollinger_reversion": "Bollinger Band Reversion",
        "donchian": "Donchian Channel",
        "rsi_reversion": "RSI Mean Reversion",
    }

    lines = ["## Strategy Signals (Independent Indicators)"]
    for key, val in strategy_signals.items():
        display_name = _KEY_TO_DISPLAY.get(key, key.replace("_", " ").title())
        signal_label = _SIGNAL_LABEL.get(int(val) if val is not None else 0, "NEUTRAL")
        lines.append(f"- {display_name}: {signal_label}")

    # Compute consensus
    non_neutral = [v for v in strategy_signals.values() if v is not None and int(v) != 0]
    total = len(strategy_signals)
    # Count signals that agree with majority direction
    longs = sum(1 for v in strategy_signals.values() if v is not None and int(v) == 1)
    shorts = sum(1 for v in strategy_signals.values() if v is not None and int(v) == -1)
    agreeing = max(longs, shorts)
    lines.append(f"Consensus: {agreeing} of {total} strategies agree on this direction")

    return "\n".join(lines)


def build_explanation_prompt(context: "SignalContext", fast_sma_period: int = 20, slow_sma_period: int = 50) -> str:
    """Build the explanation prompt for a given SignalContext."""
    news_section = _format_news_section(context.news_headlines)
    strategy_signals_section = _format_strategy_signals(context.strategy_signals)
    sr_section = _format_sr_section(context)
    volume_section = _format_volume_section(context)
    kwargs = dict(
        instrument_name=context.instrument_name,
        symbol=context.symbol,
        signal_date=context.signal_date,
        signal_direction=context.signal_direction,
        close=context.close,
        fast_sma=context.fast_sma,
        fast_sma_period=fast_sma_period,
        slow_sma=context.slow_sma,
        slow_sma_period=slow_sma_period,
        rsi=context.rsi,
        recent_trend_summary=context.recent_trend_summary,
        stop_loss_level=context.stop_loss_level,
        take_profit_level=context.take_profit_level,
        risk_reward_ratio=context.risk_reward_ratio,
        confidence_score=context.confidence_score,
        conflicting_indicators=context.conflicting_indicators,
        high_volatility=context.high_volatility,
        news_section=news_section,
        strategy_signals_section=strategy_signals_section,
        sr_section=sr_section,
        volume_section=volume_section,
    )
    if context.news_headlines:
        return EXPLANATION_PROMPT_WITH_NEWS.format(**kwargs)
    return EXPLANATION_PROMPT_NO_NEWS.format(**kwargs)


def build_decision_prompt(context: "SignalContext") -> str:
    """Build the decision prompt for a given SignalContext."""
    if context.news_headlines:
        news_section = "\n## Recent News Headlines\n" + _format_news_section(context.news_headlines)
    else:
        news_section = ""
    strategy_signals_section = _format_strategy_signals(context.strategy_signals)
    sr_section = _format_sr_section(context)
    volume_section = _format_volume_section(context)
    return DECISION_PROMPT.format(
        instrument_name=context.instrument_name,
        symbol=context.symbol,
        signal_date=context.signal_date,
        signal_direction=context.signal_direction,
        close=context.close,
        fast_sma=context.fast_sma,
        slow_sma=context.slow_sma,
        rsi=context.rsi,
        recent_trend_summary=context.recent_trend_summary,
        stop_loss_level=context.stop_loss_level,
        take_profit_level=context.take_profit_level,
        risk_reward_ratio=context.risk_reward_ratio,
        confidence_score=context.confidence_score,
        conflicting_indicators=context.conflicting_indicators,
        high_volatility=context.high_volatility,
        news_section=news_section,
        strategy_signals_section=strategy_signals_section,
        sr_section=sr_section,
        volume_section=volume_section,
    )


def build_position_management_prompt(
    context: "SignalContext",
    position_direction: str,
    entry_level: float,
    current_stop: float,
    current_target: float,
    pnl_points: float,
) -> str:
    """Build the position management prompt for an existing open position."""
    if context.news_headlines:
        news_section = "\n## Recent News Headlines\n" + _format_news_section(context.news_headlines)
    else:
        news_section = ""
    strategy_signals_section = _format_strategy_signals(context.strategy_signals)
    sr_section = _format_sr_section(context)

    pnl_direction = "profit" if pnl_points >= 0 else "loss"

    return POSITION_MANAGEMENT_PROMPT.format(
        instrument_name=context.instrument_name,
        symbol=context.symbol,
        signal_date=context.signal_date,
        close=context.close,
        fast_sma=context.fast_sma,
        slow_sma=context.slow_sma,
        rsi=context.rsi,
        recent_trend_summary=context.recent_trend_summary,
        conflicting_indicators=context.conflicting_indicators,
        high_volatility=context.high_volatility,
        news_section=news_section,
        strategy_signals_section=strategy_signals_section,
        sr_section=sr_section,
        position_direction=position_direction,
        entry_level=entry_level,
        current_stop=current_stop,
        current_target=current_target,
        pnl_points=pnl_points,
        pnl_direction=pnl_direction,
    )
