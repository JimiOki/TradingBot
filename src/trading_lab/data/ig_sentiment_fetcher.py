"""Fetch IG client sentiment and format it for LLM context.

IG client sentiment shows the % of IG clients who are currently long vs short
on a given market. This is a useful contrarian/confirmation signal for the LLM.

Requires IG credentials in .env and the instrument's ig_sentiment_id to be set
in instruments.yaml. Falls back silently if credentials are absent or the
fetch fails, so it never blocks signal generation.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def fetch_ig_sentiment_headline(instrument: dict) -> dict | None:
    """Return a news-style headline dict containing IG client sentiment.

    Args:
        instrument: instrument config dict from instruments.yaml.
                    Must have ig_sentiment_id set (e.g. "GOLD", "OIL_CRUDE").

    Returns:
        A headline dict {title, source, timestamp} compatible with
        SignalContext.news_headlines, or None if sentiment is unavailable.
    """
    # Skip if live IG credentials not configured (sentiment needs the live API)
    if not os.environ.get("IG_LIVE_API_KEY"):
        return None

    sentiment_id = instrument.get("ig_sentiment_id")
    if not sentiment_id:
        return None

    try:
        from trading_lab.execution.ig import IgBrokerAdapter
        adapter = IgBrokerAdapter(live=True)
        sentiment = adapter.fetch_sentiment(sentiment_id)
        if sentiment is None:
            return None

        # Demo API returns 0/0 for most instruments — treat as unavailable
        if sentiment.long_pct == 0.0 and sentiment.short_pct == 0.0:
            logger.debug("IG sentiment for %s returned 0%%/0%% — demo API limitation, skipping", sentiment_id)
            return None

        return {
            "title": sentiment.as_context_str(),
            "source": "IG Client Sentiment",
            "timestamp": "",
            "long_pct": sentiment.long_pct,
            "short_pct": sentiment.short_pct,
        }
    except Exception as exc:
        logger.debug("IG sentiment fetch skipped for %s: %s", instrument.get("symbol"), exc)
        return None
