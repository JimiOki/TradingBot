"""Economic calendar fetcher — retrieves upcoming high-impact events.

REQ-CTX-001: High-impact economic events within the next 5 trading days
must be surfaced on the dashboard as warnings per instrument.

Phase 1 implementation uses a free RSS/JSON feed. If the fetch fails,
returns an empty list — never propagates to dashboard.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from trading_lab.paths import CALENDAR_DIR

logger = logging.getLogger(__name__)

# Currencies that apply to all five Phase 1 commodity instruments
_COMMODITY_CURRENCIES = {"USD", "XAU", "XAG", "XTI", "XBR"}

# Investing.com free economic calendar JSON endpoint (no auth required)
_CALENDAR_URL = "https://economic-calendar.tradingeconomics.com/calendar"


def fetch_high_impact_events(
    lookforward_days: int = 5,
    cache_dir: Path = CALENDAR_DIR,
) -> list[dict]:
    """Fetch upcoming high-impact economic events.

    Args:
        lookforward_days: Number of days ahead to look.
        cache_dir:        Directory for caching today's events.

    Returns:
        List of event dicts: {name, date, time_utc, currency, impact}.
        Empty list if fetch fails.
    """
    today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    cache_path = cache_dir / f"events_{today_str}.json"

    # Return cached data if available
    if cache_path.exists():
        try:
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Calendar cache read failed: %s", exc)

    events = _fetch_from_source(lookforward_days)

    # Persist to cache
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(events, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("Calendar cache write failed: %s", exc)

    return events


def _fetch_from_source(lookforward_days: int) -> list[dict]:
    """Fetch events from the remote source. Returns empty list on any error."""
    try:
        import urllib.request
        import urllib.parse
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        end = now + timedelta(days=lookforward_days)
        params = urllib.parse.urlencode({
            "c": "g10",
            "d1": now.strftime("%Y-%m-%d"),
            "d2": end.strftime("%Y-%m-%d"),
        })
        url = f"{_CALENDAR_URL}?{params}"

        req = urllib.request.Request(url, headers={"User-Agent": "trading-lab/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read().decode())

        events = []
        for item in (raw if isinstance(raw, list) else []):
            impact = str(item.get("importance", "")).lower()
            if impact not in ("3", "high"):
                continue
            events.append({
                "name": item.get("event", item.get("name", "")),
                "date": item.get("date", ""),
                "time_utc": item.get("date", ""),
                "currency": item.get("currency", item.get("country", "")),
                "impact": "high",
            })
        return events

    except Exception as exc:
        logger.warning("Calendar fetch failed: %s", exc)
        return []
