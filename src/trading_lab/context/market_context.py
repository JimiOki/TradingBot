"""MarketContext aggregator — assembles per-instrument context for the LLM layer.

REQ-CONTEXT-001: MarketContext combines session status, upcoming events,
and news headlines into a single structure persisted alongside the signal snapshot.
REQ-CONTEXT-002: MarketContext is written during the signals run, not on page load.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_lab.paths import SIGNALS_DATA_DIR

logger = logging.getLogger(__name__)


@dataclass
class MarketContext:
    """Per-instrument market context snapshot.

    REQ-CONTEXT-001: All fields are populated during the signals run.
    ig_sentiment is always None in Phase 1; populated in Phase 2 via IgBrokerAdapter.
    """
    symbol: str
    as_of: datetime
    session_open: bool
    upcoming_events: list[dict] = field(default_factory=list)
    news_headlines: list[dict] = field(default_factory=list)
    ig_sentiment: Any = None      # Phase 2: IGSentiment dataclass


def build_market_context(
    symbol: str,
    instrument_config: dict,
    events: list[dict],
    news: list[dict],
    session_open: bool | None = None,
    now: datetime | None = None,
) -> MarketContext:
    """Assemble a MarketContext from components.

    Args:
        symbol:            Instrument symbol.
        instrument_config: Instrument dict from instruments.yaml.
        events:            High-impact events from calendar_fetcher.
        news:              News headlines from fetch_news.
        session_open:      Override session status (computed if None).
        now:               Override current time (defaults to utcnow).

    Returns:
        Populated MarketContext.
    """
    from trading_lab.context.session_checker import is_session_open as _is_open

    if now is None:
        now = datetime.now(timezone.utc)

    if session_open is None:
        session_open = _is_open(instrument_config, now=now)

    return MarketContext(
        symbol=symbol,
        as_of=now,
        session_open=session_open,
        upcoming_events=events or [],
        news_headlines=news or [],
        ig_sentiment=None,
    )


def persist_market_context(context: MarketContext, output_dir: Path = SIGNALS_DATA_DIR) -> Path:
    """Write MarketContext to disk as JSON.

    Path: <output_dir>/market_context_<symbol>_<YYYYMMDD>.json
    """
    date_str = context.as_of.strftime("%Y%m%d")
    path = output_dir / f"market_context_{context.symbol}_{date_str}.json"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "symbol": context.symbol,
            "as_of": context.as_of.isoformat(),
            "session_open": context.session_open,
            "upcoming_events": context.upcoming_events,
            "news_headlines": context.news_headlines,
            "ig_sentiment": None,
        }
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to persist MarketContext for %s: %s", context.symbol, exc)
    return path


def load_market_context(symbol: str, date_str: str, input_dir: Path = SIGNALS_DATA_DIR) -> MarketContext | None:
    """Load a persisted MarketContext from disk. Returns None if not found."""
    path = input_dir / f"market_context_{symbol}_{date_str}.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return MarketContext(
            symbol=data["symbol"],
            as_of=datetime.fromisoformat(data["as_of"]),
            session_open=data["session_open"],
            upcoming_events=data.get("upcoming_events", []),
            news_headlines=data.get("news_headlines", []),
            ig_sentiment=None,
        )
    except (OSError, KeyError, ValueError) as exc:
        logger.warning("Failed to load MarketContext for %s %s: %s", symbol, date_str, exc)
        return None
