"""Tests for src/trading_lab/context/"""
import json
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

from trading_lab.context.session_checker import is_session_open
from trading_lab.context.market_context import (
    build_market_context,
    persist_market_context,
    load_market_context,
    MarketContext,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NY_TZ = ZoneInfo("America/New_York")

_REGULAR_INSTRUMENT = {
    "symbol": "GC=F",
    "session_open": "09:00",
    "session_close": "17:00",
    "session_timezone": "America/New_York",
}

_OVERNIGHT_INSTRUMENT = {
    "symbol": "GC=F",
    "session_open": "18:00",
    "session_close": "17:00",
    "session_timezone": "America/New_York",
}


# ---------------------------------------------------------------------------
# session_checker tests
# ---------------------------------------------------------------------------

def test_session_open_within_hours():
    """Weekday, time within open/close range → True."""
    # Wednesday 2024-01-10 at 10:00 NY time
    now = datetime(2024, 1, 10, 10, 0, tzinfo=NY_TZ)
    assert is_session_open(_REGULAR_INSTRUMENT, now=now) is True


def test_session_closed_before_open():
    """Weekday, time before open → False."""
    # Wednesday 2024-01-10 at 08:00 NY time (before 09:00 open)
    now = datetime(2024, 1, 10, 8, 0, tzinfo=NY_TZ)
    assert is_session_open(_REGULAR_INSTRUMENT, now=now) is False


def test_session_closed_after_close():
    """Weekday, time after close → False."""
    # Wednesday 2024-01-10 at 18:00 NY time (after 17:00 close)
    now = datetime(2024, 1, 10, 18, 0, tzinfo=NY_TZ)
    assert is_session_open(_REGULAR_INSTRUMENT, now=now) is False


def test_session_closed_on_saturday():
    """Saturday → False regardless of time."""
    # Saturday 2024-01-13 at 10:00 NY time
    now = datetime(2024, 1, 13, 10, 0, tzinfo=NY_TZ)
    assert is_session_open(_REGULAR_INSTRUMENT, now=now) is False


def test_session_closed_on_sunday():
    """Sunday → False."""
    # Sunday 2024-01-14 at 10:00 NY time
    now = datetime(2024, 1, 14, 10, 0, tzinfo=NY_TZ)
    assert is_session_open(_REGULAR_INSTRUMENT, now=now) is False


def test_overnight_session_open_after_open_time():
    """Overnight session (18:00 open, 17:00 close), current time 20:00 Wednesday → True."""
    now = datetime(2024, 1, 10, 20, 0, tzinfo=NY_TZ)  # Wednesday
    assert is_session_open(_OVERNIGHT_INSTRUMENT, now=now) is True


def test_overnight_session_open_before_close_time():
    """Overnight session (18:00 open, 17:00 close), current time 03:00 Thursday → True."""
    now = datetime(2024, 1, 11, 3, 0, tzinfo=NY_TZ)  # Thursday
    assert is_session_open(_OVERNIGHT_INSTRUMENT, now=now) is True


def test_overnight_session_closed_between_close_and_open():
    """Overnight session (18:00 open, 17:00 close), current time 17:30 Wednesday → False."""
    now = datetime(2024, 1, 10, 17, 30, tzinfo=NY_TZ)  # Wednesday
    assert is_session_open(_OVERNIGHT_INSTRUMENT, now=now) is False


def test_session_open_returns_true_when_no_times_configured():
    """Instrument with no session_open/session_close on a weekday → True."""
    instrument = {
        "symbol": "TEST",
        "session_timezone": "America/New_York",
        # no session_open or session_close
    }
    now = datetime(2024, 1, 10, 10, 0, tzinfo=NY_TZ)  # Wednesday
    assert is_session_open(instrument, now=now) is True


# ---------------------------------------------------------------------------
# market_context tests
# ---------------------------------------------------------------------------

def test_build_market_context_populates_all_fields():
    """build_market_context returns a MarketContext with all expected fields."""
    now = datetime(2024, 1, 10, 10, 0, tzinfo=ZoneInfo("UTC"))
    events = [{"name": "NFP", "date": "2024-01-12", "time_utc": "2024-01-12T13:30:00Z", "currency": "USD", "impact": "high"}]
    news = [{"title": "Gold surges", "source": "Reuters", "timestamp": "2024-01-10T09:00:00Z"}]

    ctx = build_market_context(
        symbol="GC=F",
        instrument_config=_OVERNIGHT_INSTRUMENT,
        events=events,
        news=news,
        now=now,
    )

    assert isinstance(ctx, MarketContext)
    assert ctx.symbol == "GC=F"
    assert ctx.as_of == now
    assert isinstance(ctx.session_open, bool)
    assert ctx.upcoming_events == events
    assert ctx.news_headlines == news
    assert ctx.ig_sentiment is None


def test_persist_and_load_market_context(tmp_path):
    """Write MarketContext to disk then read it back — verify roundtrip."""
    now = datetime(2024, 1, 10, 10, 0, tzinfo=ZoneInfo("UTC"))
    events = [{"name": "CPI", "date": "2024-01-11", "time_utc": "2024-01-11T13:30:00Z", "currency": "USD", "impact": "high"}]
    news = [{"title": "Oil drops", "source": "Bloomberg", "timestamp": "2024-01-10T08:00:00Z"}]

    ctx = MarketContext(
        symbol="CL=F",
        as_of=now,
        session_open=True,
        upcoming_events=events,
        news_headlines=news,
        ig_sentiment=None,
    )

    path = persist_market_context(ctx, output_dir=tmp_path)
    assert path.exists()

    loaded = load_market_context("CL=F", "20240110", input_dir=tmp_path)
    assert loaded is not None
    assert loaded.symbol == "CL=F"
    assert loaded.session_open is True
    assert loaded.upcoming_events == events
    assert loaded.news_headlines == news
    assert loaded.ig_sentiment is None
    assert loaded.as_of.isoformat() == now.isoformat()


def test_load_market_context_returns_none_when_not_found(tmp_path):
    """load_market_context returns None when the file does not exist."""
    result = load_market_context("GC=F", "20240101", input_dir=tmp_path)
    assert result is None


def test_market_context_ig_sentiment_is_none():
    """ig_sentiment is always None in Phase 1."""
    now = datetime(2024, 1, 10, 10, 0, tzinfo=ZoneInfo("UTC"))
    ctx = build_market_context(
        symbol="SI=F",
        instrument_config=_OVERNIGHT_INSTRUMENT,
        events=[],
        news=[],
        session_open=True,
        now=now,
    )
    assert ctx.ig_sentiment is None


# ---------------------------------------------------------------------------
# calendar_fetcher tests (mocked network)
# ---------------------------------------------------------------------------

def test_fetch_high_impact_events_uses_cache(tmp_path):
    """Pre-write a cache file — fetch_high_impact_events should return it without HTTP call."""
    from trading_lab.context.calendar_fetcher import fetch_high_impact_events
    from datetime import timezone

    today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    cache_file = tmp_path / f"events_{today_str}.json"
    cached_events = [
        {"name": "FOMC", "date": "2024-01-10", "time_utc": "2024-01-10T19:00:00Z", "currency": "USD", "impact": "high"}
    ]
    cache_file.write_text(json.dumps(cached_events), encoding="utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        result = fetch_high_impact_events(cache_dir=tmp_path)

    mock_urlopen.assert_not_called()
    assert result == cached_events


def test_fetch_high_impact_events_returns_empty_on_error(tmp_path):
    """When HTTP fetch fails, fetch_high_impact_events returns an empty list."""
    from trading_lab.context.calendar_fetcher import fetch_high_impact_events

    with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        result = fetch_high_impact_events(cache_dir=tmp_path)

    assert result == []
