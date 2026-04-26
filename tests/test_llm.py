"""Tests for the LLM layer — build-plan Step 3.9.

Covers:
- StubLLMClient behaviour
- ClaudeClient configuration error
- ExplanationService: cache hit/miss, fallback on failure, timeout fallback
- DecisionService: GO/NO_GO/UNCERTAIN parsing, cache hit, parse failure fallback
- fetch_news: error handling, cap at max_headlines
- build_signal_context: LONG and SHORT directions
- prompt builders: news-present and news-absent branches
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from trading_lab.data.yfinance_ingest import fetch_news
from trading_lab.exceptions import ConfigurationError, LLMError, LLMTimeoutError
from trading_lab.llm.base import LLMClient
from trading_lab.llm.context import SignalContext, build_signal_context
from trading_lab.llm.decision import DecisionService
from trading_lab.llm.explainer import EXPLANATION_UNAVAILABLE, ExplanationService
from trading_lab.llm.prompts import build_decision_prompt, build_explanation_prompt
from trading_lab.llm.stub_client import STUB_RESPONSE, StubLLMClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(news=None) -> SignalContext:
    return SignalContext(
        symbol="GC=F",
        instrument_name="Gold",
        signal_date=date(2024, 1, 15),
        signal=1,
        signal_direction="LONG",
        close=1950.0,
        fast_sma=1940.0,
        slow_sma=1920.0,
        rsi=55.0,
        recent_trend_summary="Close is 0.5% above fast SMA",
        stop_loss_level=1910.0,
        take_profit_level=1990.0,
        risk_reward_ratio=2.0,
        confidence_score=75,
        conflicting_indicators=False,
        high_volatility=False,
        news_headlines=news or [],
    )


class _MockLLMClient(LLMClient):
    """Records calls and returns a configurable response."""

    def __init__(self, response: str = "Test explanation."):
        self.response = response
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        return self.response


class _FailingLLMClient(LLMClient):
    """Always raises LLMError."""

    def complete(self, prompt: str) -> str:
        raise LLMError("API down")


class _TimeoutLLMClient(LLMClient):
    """Always raises LLMTimeoutError."""

    def complete(self, prompt: str) -> str:
        raise LLMTimeoutError("Timed out")


# ---------------------------------------------------------------------------
# StubLLMClient tests
# ---------------------------------------------------------------------------


def test_stub_client_returns_fixed_string():
    client = StubLLMClient()
    result = client.complete("any prompt")
    assert result == STUB_RESPONSE
    assert result == "[Stub explanation — LLM not configured]"


# ---------------------------------------------------------------------------
# ClaudeClient configuration tests
# ---------------------------------------------------------------------------


def test_missing_api_key_raises_configuration_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from trading_lab.llm.claude_client import ClaudeClient

    with pytest.raises(ConfigurationError):
        ClaudeClient()


# ---------------------------------------------------------------------------
# ExplanationService — cache hit
# ---------------------------------------------------------------------------


def test_cache_hit_does_not_call_llm(tmp_path):
    mock_client = _MockLLMClient("Fresh explanation.")
    service = ExplanationService(client=mock_client, cache_dir=tmp_path)

    # Pre-populate the cache
    cache_data = {
        "symbol": "GC=F",
        "signal_date": "2024-01-15",
        "signal": 1,
        "explanation": "Cached explanation text.",
        "generated_at": "2024-01-15T12:00:00+00:00",
        "model": "stub",
    }
    cache_path = tmp_path / "GC=F_2024-01-15.json"
    cache_path.write_text(json.dumps(cache_data), encoding="utf-8")

    context = _make_context()
    result = service.get_or_generate(context)

    assert mock_client.calls == 0
    assert result.explanation == "Cached explanation text."
    assert result.cached is True


def test_explanation_cache_hit_returns_cached_true(tmp_path):
    mock_client = _MockLLMClient()
    service = ExplanationService(client=mock_client, cache_dir=tmp_path)

    cache_data = {
        "symbol": "GC=F",
        "signal_date": "2024-01-15",
        "signal": 1,
        "explanation": "Some cached explanation.",
        "generated_at": "2024-01-15T10:00:00+00:00",
        "model": "stub",
    }
    (tmp_path / "GC=F_2024-01-15.json").write_text(
        json.dumps(cache_data), encoding="utf-8"
    )

    context = _make_context()
    result = service.get_or_generate(context)

    assert result.cached is True


# ---------------------------------------------------------------------------
# ExplanationService — cache miss
# ---------------------------------------------------------------------------


def test_cache_miss_calls_llm_and_writes_cache(tmp_path):
    mock_client = _MockLLMClient("Fresh LLM explanation.")
    service = ExplanationService(client=mock_client, cache_dir=tmp_path)

    context = _make_context()
    result = service.get_or_generate(context)

    assert mock_client.calls == 1
    assert result.explanation == "Fresh LLM explanation."
    assert result.cached is False

    # Cache file must have been written
    cache_path = tmp_path / "GC=F_2024-01-15.json"
    assert cache_path.exists()
    persisted = json.loads(cache_path.read_text(encoding="utf-8"))
    assert persisted["explanation"] == "Fresh LLM explanation."


# ---------------------------------------------------------------------------
# ExplanationService — failure fallbacks
# ---------------------------------------------------------------------------


def test_api_failure_returns_fallback_explanation(tmp_path):
    service = ExplanationService(client=_FailingLLMClient(), cache_dir=tmp_path)
    context = _make_context()
    result = service.get_or_generate(context)

    assert result.explanation == EXPLANATION_UNAVAILABLE
    assert result.explanation == "Explanation unavailable."
    assert result.cached is False


def test_explanation_returns_unavailable_on_timeout(tmp_path):
    service = ExplanationService(client=_TimeoutLLMClient(), cache_dir=tmp_path)
    context = _make_context()
    result = service.get_or_generate(context)

    assert result.explanation == EXPLANATION_UNAVAILABLE


# ---------------------------------------------------------------------------
# DecisionService — parsing
# ---------------------------------------------------------------------------


def test_decision_go_parsed_correctly(tmp_path):
    payload = json.dumps(
        {
            "recommendation": "GO",
            "rationale": "Signal is clear.",
            "conflicts_with_technical": False,
        }
    )
    mock_client = _MockLLMClient(payload)
    service = DecisionService(client=mock_client, cache_dir=tmp_path)

    result = service.get_or_generate(_make_context())

    assert result.llm_recommendation == "GO"
    assert result.rationale == "Signal is clear."
    assert result.conflicts_with_technical is False
    assert result.cached is False


def test_decision_no_go_parsed_correctly(tmp_path):
    payload = json.dumps(
        {
            "recommendation": "NO_GO",
            "rationale": "RSI is overbought.",
            "conflicts_with_technical": True,
        }
    )
    mock_client = _MockLLMClient(payload)
    service = DecisionService(client=mock_client, cache_dir=tmp_path)

    result = service.get_or_generate(_make_context())

    assert result.llm_recommendation == "NO_GO"
    assert result.rationale == "RSI is overbought."
    assert result.conflicts_with_technical is True


def test_decision_no_go_is_first_class_outcome(tmp_path):
    """UNCERTAIN returned when evidence is mixed / parse fails."""
    service = DecisionService(client=_FailingLLMClient(), cache_dir=tmp_path)
    result = service.get_or_generate(_make_context())

    assert result.llm_recommendation == "UNCERTAIN"
    assert result.rationale == "Decision unavailable."


def test_decision_parse_failure_falls_back_to_uncertain(tmp_path):
    """Plain text (non-JSON) response causes parse failure, falls back to UNCERTAIN."""
    mock_client = _MockLLMClient("I cannot determine this.")
    service = DecisionService(client=mock_client, cache_dir=tmp_path)

    result = service.get_or_generate(_make_context())

    assert result.llm_recommendation == "UNCERTAIN"
    assert result.rationale == "Decision unavailable."


# ---------------------------------------------------------------------------
# DecisionService — cache hit
# ---------------------------------------------------------------------------


def test_decision_cached_returns_cached_true(tmp_path):
    mock_client = _MockLLMClient()
    service = DecisionService(client=mock_client, cache_dir=tmp_path)

    cache_data = {
        "symbol": "GC=F",
        "signal_date": "2024-01-15",
        "signal": 1,
        "llm_recommendation": "GO",
        "rationale": "Trend confirmed.",
        "conflicts_with_technical": False,
        "generated_at": "2024-01-15T12:00:00+00:00",
        "model": "stub",
    }
    (tmp_path / "GC=F_2024-01-15.json").write_text(
        json.dumps(cache_data), encoding="utf-8"
    )

    result = service.get_or_generate(_make_context())

    assert result.cached is True
    assert mock_client.calls == 0
    assert result.llm_recommendation == "GO"


# ---------------------------------------------------------------------------
# fetch_news tests
# ---------------------------------------------------------------------------


def test_fetch_news_empty_list_on_error():
    with patch("trading_lab.data.yfinance_ingest.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.news = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("network error"))
        )
        # Use a side_effect on the news attribute instead
        instance = MagicMock()
        type(instance).news = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("network error"))
        )
        mock_ticker.return_value = instance

        result = fetch_news("GC=F")

    assert result == []


def test_fetch_news_capped_at_max_headlines():
    fake_news = [
        {
            "title": f"Headline {i}",
            "publisher": f"Source {i}",
            "providerPublishTime": f"2024-01-{i + 1:02d}",
        }
        for i in range(10)
    ]
    with patch("trading_lab.data.yfinance_ingest.yf.Ticker") as mock_ticker:
        instance = MagicMock()
        instance.news = fake_news
        mock_ticker.return_value = instance

        result = fetch_news("GC=F", max_headlines=3)

    assert len(result) == 3
    assert result[0]["title"] == "Headline 0"
    assert result[2]["title"] == "Headline 2"


# ---------------------------------------------------------------------------
# build_signal_context tests
# ---------------------------------------------------------------------------


def test_signal_context_all_fields_populated():
    signal_row = {
        "signal": 1,
        "signal_date": date(2024, 1, 15),
        "close": 1950.0,
        "fast_sma": 1940.0,
        "slow_sma": 1920.0,
        "rsi": 55.0,
        "stop_loss_level": 1910.0,
        "take_profit_level": 1990.0,
        "confidence_score": 75,
        "conflicting_indicators": False,
        "high_volatility": False,
    }
    instrument = {"symbol": "GC=F", "name": "Gold"}
    news = [{"title": "Gold rises", "source": "Reuters", "timestamp": "2024-01-15"}]

    ctx = build_signal_context(signal_row, instrument, news)

    assert ctx.symbol == "GC=F"
    assert ctx.instrument_name == "Gold"
    assert ctx.signal == 1
    assert ctx.signal_direction == "LONG"
    assert ctx.close == 1950.0
    assert ctx.fast_sma == 1940.0
    assert ctx.slow_sma == 1920.0
    assert ctx.rsi == 55.0
    assert ctx.stop_loss_level == 1910.0
    assert ctx.take_profit_level == 1990.0
    assert ctx.confidence_score == 75
    assert ctx.conflicting_indicators is False
    assert ctx.high_volatility is False
    assert len(ctx.news_headlines) == 1
    assert ctx.news_headlines[0]["title"] == "Gold rises"
    assert ctx.risk_reward_ratio > 0
    assert ctx.recent_trend_summary != ""


def test_build_signal_context_long_direction():
    signal_row = {
        "signal": 1,
        "signal_date": date(2024, 1, 15),
        "close": 1950.0,
        "fast_sma": 1940.0,
        "slow_sma": 1920.0,
        "rsi": 55.0,
        "stop_loss_level": 1910.0,
        "take_profit_level": 1990.0,
        "confidence_score": 70,
        "conflicting_indicators": False,
        "high_volatility": False,
    }
    ctx = build_signal_context(signal_row, {"symbol": "GC=F", "name": "Gold"}, [])

    assert ctx.signal == 1
    assert ctx.signal_direction == "LONG"


def test_build_signal_context_short_direction():
    signal_row = {
        "signal": -1,
        "signal_date": date(2024, 1, 15),
        "close": 1950.0,
        "fast_sma": 1960.0,
        "slow_sma": 1980.0,
        "rsi": 70.0,
        "stop_loss_level": 1990.0,
        "take_profit_level": 1910.0,
        "confidence_score": 60,
        "conflicting_indicators": True,
        "high_volatility": True,
    }
    ctx = build_signal_context(signal_row, {"symbol": "GC=F", "name": "Gold"}, [])

    assert ctx.signal == -1
    assert ctx.signal_direction == "SHORT"


# ---------------------------------------------------------------------------
# Prompt builder tests
# ---------------------------------------------------------------------------


def test_build_explanation_prompt_with_news_contains_news():
    news = [
        {
            "title": "Gold hits new high",
            "source": "Reuters",
            "timestamp": "2024-01-15",
        }
    ]
    context = _make_context(news=news)
    prompt = build_explanation_prompt(context)

    assert "Gold hits new high" in prompt
    assert "Reuters" in prompt
    # With-news template includes a news context section
    assert "News" in prompt


def test_build_explanation_prompt_no_news_used_when_no_headlines():
    context = _make_context(news=[])
    prompt = build_explanation_prompt(context)

    # No-news template does not have the "Recent News Headlines" section
    assert "Recent News Headlines" not in prompt
    # But it does still describe the signal
    assert "LONG" in prompt
    assert "GC=F" in prompt
