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
You are a systematic trader with discretionary override capability. \
You have been given technical signals and market news for {instrument_name} ({symbol}). \
Make a clear trading decision: GO (act on the signal), NO_GO (stand aside), or \
UNCERTAIN (insufficient conviction). Be decisive — UNCERTAIN should only be used \
when evidence genuinely points in two directions equally.

## Technical Signal
- Signal Date: {signal_date}
- Direction: {signal_direction}
- Close: {close:.4f} | Fast SMA: {fast_sma:.4f} | Slow SMA: {slow_sma:.4f}
- RSI (14): {rsi:.1f} | Trend: {recent_trend_summary}
- Stop: {stop_loss_level:.4f} | Target: {take_profit_level:.4f} | R/R: {risk_reward_ratio:.1f}x
- Confidence: {confidence_score}/100 | Conflicting: {conflicting_indicators} | Volatile: {high_volatility}

{strategy_signals_section}
{news_section}

## Decision Rules
- 4-6 strategies agreeing → strong technical case, lean GO unless news is a clear headwind
- 2-3 strategies agreeing → moderate case, news and sentiment become the deciding factor
- 0-1 strategies agreeing → weak technical case, only GO if news provides a strong catalyst
- If news identifies a specific macro risk (rate decision, geopolitical event, earnings) \
  that directly affects this instrument, weight it heavily — it may override the technicals
- If IG client sentiment strongly opposes the signal direction (>70% on opposite side), \
  treat this as a contrarian flag worth noting

Respond ONLY with a JSON object. No text outside the JSON.

Required format:
{{
  "recommendation": "GO" | "NO_GO" | "UNCERTAIN",
  "rationale": "2-3 sentences: state the key technical driver, the most relevant news catalyst, and why you landed on this decision",
  "conflicts_with_technical": true | false
}}
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
