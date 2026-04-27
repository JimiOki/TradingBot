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

## Your Analysis (3-4 sentences)
Explain what the technical picture is saying, how strong the conviction is given \
the strategy consensus, and what the main risk to this signal is.
"""

DECISION_PROMPT = """\
You are a discretionary trader making a trading decision for {instrument_name} ({symbol}). \
You have been given technical evidence, news, and market sentiment. Your job is to weigh \
all of it and reach a conviction. The technical signals are one input — not the answer.

## Technical Evidence
- Date: {signal_date}
- Close: {close:.4f} | Fast SMA: {fast_sma:.4f} | Slow SMA: {slow_sma:.4f}
- RSI (14): {rsi:.1f} | Trend: {recent_trend_summary}
- Suggested Stop: {stop_loss_level:.4f} | Suggested Target: {take_profit_level:.4f} | R/R: {risk_reward_ratio:.1f}x
- Conflicting Indicators: {conflicting_indicators} | High Volatility: {high_volatility}

{strategy_signals_section}
{news_section}

## How to reason
- Weigh the technical consensus, news catalysts, and sentiment together — no single input wins automatically
- A strong macro catalyst in the news can justify a direction that conflicts with weak technicals, and vice versa
- If IG client sentiment strongly opposes your intended direction (>70% on the other side), note it — \
  it may be a contrarian signal or a warning
- UNCERTAIN should only be used when evidence genuinely pulls equally in both directions — be decisive

Respond ONLY with a JSON object. No text outside the JSON.

Required format:
{{
  "recommendation": "GO" | "NO_GO" | "UNCERTAIN",
  "direction": "LONG" | "SHORT" | null,
  "rationale": "2-3 sentences covering the key technical picture, the most relevant news or sentiment factor, and why you landed here",
  "conflicts_with_technical": true | false
}}

direction must be set to LONG or SHORT when recommendation is GO, and null otherwise.
"""


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
    )
