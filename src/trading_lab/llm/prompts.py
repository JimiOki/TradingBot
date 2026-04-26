"""Prompt templates for the LLM explanation and decision layers.

All templates are module-level string constants. They are not embedded in classes.
Both explanation prompts instruct the LLM to:
  - Write 3-5 sentences in plain English
  - Not make price predictions or give investment advice
  - Be directionally consistent with the signal
"""

EXPLANATION_PROMPT_WITH_NEWS = """\
You are a trading signal analyst. Write a 3-5 sentence explanation of the following \
trading signal in plain English. Do not make price predictions or give investment advice. \
Be directionally consistent with the signal direction stated below.

## Signal Details
- Instrument: {instrument_name} ({symbol})
- Signal Date: {signal_date}
- Signal Direction: {signal_direction}
- Close Price: {close:.4f}
- Fast SMA ({fast_sma_period}): {fast_sma:.4f}
- Slow SMA ({slow_sma_period}): {slow_sma:.4f}
- RSI (14): {rsi:.1f}
- Recent Trend: {recent_trend_summary}
- Stop Loss: {stop_loss_level:.4f}
- Take Profit: {take_profit_level:.4f}
- Risk/Reward: {risk_reward_ratio:.1f}x
- Confidence Score: {confidence_score}/100
- Conflicting Indicators: {conflicting_indicators}
- High Volatility: {high_volatility}

## Recent News Headlines
{news_section}

## Instructions
Part 1 — Technical basis: Explain in 2-3 sentences why this signal fired based on the \
indicator readings above.
Part 2 — News context: In 1-2 sentences, state whether the news headlines above support, \
contradict, or are neutral relative to the {signal_direction} signal direction. If the news \
contradicts the technical signal, you MUST explicitly flag this tension.
"""

EXPLANATION_PROMPT_NO_NEWS = """\
You are a trading signal analyst. Write a 3-5 sentence explanation of the following \
trading signal in plain English. Do not make price predictions or give investment advice. \
Be directionally consistent with the signal direction stated below.

## Signal Details
- Instrument: {instrument_name} ({symbol})
- Signal Date: {signal_date}
- Signal Direction: {signal_direction}
- Close Price: {close:.4f}
- Fast SMA ({fast_sma_period}): {fast_sma:.4f}
- Slow SMA ({slow_sma_period}): {slow_sma:.4f}
- RSI (14): {rsi:.1f}
- Recent Trend: {recent_trend_summary}
- Stop Loss: {stop_loss_level:.4f}
- Take Profit: {take_profit_level:.4f}
- Risk/Reward: {risk_reward_ratio:.1f}x
- Confidence Score: {confidence_score}/100
- Conflicting Indicators: {conflicting_indicators}
- High Volatility: {high_volatility}

Explain in 3-5 sentences why this signal fired based on the indicator readings above. \
Focus on the technical drivers: SMA crossover, RSI position, and signal strength.
"""

DECISION_PROMPT = """\
You are a trading signal review assistant. Evaluate the following trading signal and \
return a structured JSON response. Do not give investment advice or make price predictions.

## Signal Details
- Instrument: {instrument_name} ({symbol})
- Signal Date: {signal_date}
- Signal Direction: {signal_direction}
- Close Price: {close:.4f}
- Fast SMA: {fast_sma:.4f}
- Slow SMA: {slow_sma:.4f}
- RSI (14): {rsi:.1f}
- Recent Trend: {recent_trend_summary}
- Stop Loss: {stop_loss_level:.4f}
- Take Profit: {take_profit_level:.4f}
- Risk/Reward: {risk_reward_ratio:.1f}x
- Confidence Score: {confidence_score}/100
- Conflicting Indicators: {conflicting_indicators}
- High Volatility: {high_volatility}
{news_section}

## Instructions
Respond ONLY with a JSON object. No explanation outside the JSON.
"NO_GO" and "UNCERTAIN" are first-class outcomes — prefer them over a forced "GO" when \
evidence is mixed.

Required format:
{{
  "recommendation": "GO" | "NO_GO" | "UNCERTAIN",
  "rationale": "1-3 sentence rationale",
  "conflicts_with_technical": true | false
}}
"""


def _format_news_section(headlines: list[dict]) -> str:
    """Format a list of news headline dicts into a readable string."""
    if not headlines:
        return "No recent news headlines available."
    lines = []
    for h in headlines:
        ts = h.get("timestamp", "")
        title = h.get("title", "")
        source = h.get("source", "")
        lines.append(f"- [{ts}] {title} ({source})")
    return "\n".join(lines)


def build_explanation_prompt(context: "SignalContext", fast_sma_period: int = 20, slow_sma_period: int = 50) -> str:
    """Build the explanation prompt for a given SignalContext."""
    news_section = _format_news_section(context.news_headlines)
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
    )
