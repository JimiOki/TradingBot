"""Market session awareness — determines if an instrument's market session is open.

REQ-CTX-002: Each instrument has a session_open and session_close time in its
session_timezone. Weekends are always CLOSED. No holiday calendar in Phase 1.
"""
from __future__ import annotations

import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def is_session_open(instrument: dict, now: datetime | None = None) -> bool:
    """Return True if the instrument's market session is currently open.

    Args:
        instrument: Instrument config dict with keys:
                    session_open (HH:MM), session_close (HH:MM),
                    session_timezone (IANA timezone string).
        now:        Override the current time (UTC-aware). Defaults to utcnow().

    Returns:
        True if the session is open, False otherwise.
        Always False on Saturday (weekday=5) or Sunday (weekday=6).
    """
    if now is None:
        now = datetime.now(ZoneInfo("UTC"))

    tz_name = instrument.get("session_timezone", "UTC")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        logger.warning("Unknown timezone '%s' for instrument %s", tz_name, instrument.get("symbol"))
        return False

    local_now = now.astimezone(tz)

    # Weekends always closed
    if local_now.weekday() >= 5:
        return False

    session_open_str = instrument.get("session_open", "")
    session_close_str = instrument.get("session_close", "")

    if not session_open_str or not session_close_str:
        # No session times configured — assume open on weekdays
        return True

    try:
        open_h, open_m = map(int, session_open_str.split(":"))
        close_h, close_m = map(int, session_close_str.split(":"))
    except (ValueError, AttributeError):
        logger.warning(
            "Invalid session times for %s: open=%s close=%s",
            instrument.get("symbol"), session_open_str, session_close_str,
        )
        return False

    open_t = time(open_h, open_m)
    close_t = time(close_h, close_m)
    current_t = local_now.time().replace(second=0, microsecond=0)

    # Handle overnight sessions (e.g. 18:00 open, 17:00 close next day)
    if open_t <= close_t:
        return open_t <= current_t < close_t
    else:
        # Overnight: open if >= open_t OR < close_t
        return current_t >= open_t or current_t < close_t
