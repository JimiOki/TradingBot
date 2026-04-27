"""Structured audit log for the trading-lab system.

REQ-OPS-001: Every signal generated, every user action (approve/reject), and every
LLM API call must be recorded with enough detail to reconstruct the decision trail.

Log format: JSON-lines (one JSON object per line) at logs/audit.log.
The file is append-only and is never truncated by application code.

Usage::

    from trading_lab.audit import log_event, AuditAction

    log_event(AuditAction.SIGNAL_GENERATED, instrument="GC=F", values={"signal": 1})
    log_event(AuditAction.LLM_CALL_MADE, instrument="GC=F", values={"response_ms": 342})
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_lab.paths import LOGS_DIR, ensure_data_dirs

logger = logging.getLogger(__name__)

# Path to the audit log file — append-only, never truncated.
AUDIT_LOG_PATH = LOGS_DIR / "audit.log"

# Valid action strings — enforced at call time.
# Extend this list when new auditable events are introduced.


class AuditAction:
    """Namespace for valid audit action strings (REQ-OPS-001)."""

    SIGNAL_GENERATED = "signal_generated"
    SIGNAL_APPROVED = "signal_approved"
    SIGNAL_REJECTED = "signal_rejected"
    LLM_CALL_MADE = "llm_call_made"
    LLM_CALL_CACHED = "llm_call_cached"
    LLM_CALL_FAILED = "llm_call_failed"
    ORDER_PLACED = "order_placed"
    ORDER_SKIPPED = "order_skipped"

    _ALL = {
        SIGNAL_GENERATED,
        SIGNAL_APPROVED,
        SIGNAL_REJECTED,
        LLM_CALL_MADE,
        LLM_CALL_CACHED,
        LLM_CALL_FAILED,
        ORDER_PLACED,
        ORDER_SKIPPED,
    }

    @classmethod
    def validate(cls, action: str) -> None:
        if action not in cls._ALL:
            raise ValueError(
                f"Unknown audit action '{action}'. "
                f"Valid actions: {sorted(cls._ALL)}"
            )


def log_event(
    action: str,
    instrument: str,
    values: dict[str, Any],
    *,
    audit_path: Path | None = None,
) -> None:
    """Append a structured audit entry to the audit log.

    REQ-OPS-001 acceptance criteria:
    - Every entry contains: timestamp (ISO 8601 UTC), instrument, action, values.
    - The file is appended; never overwritten or truncated.
    - Entries older than 90 days are not auto-deleted.

    Args:
        action:     One of the AuditAction constants.
        instrument: Instrument symbol (e.g. 'GC=F'). Must be non-empty.
        values:     Dict of action-specific fields (e.g. signal direction, response time).
        audit_path: Override the default log path (used in tests).

    Raises:
        ValueError: If action is not a recognised AuditAction value, or
                    instrument is empty.
    """
    AuditAction.validate(action)
    if not instrument:
        raise ValueError("instrument must be a non-empty string.")

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "instrument": instrument,
        "action": action,
        "values": values,
    }

    path = audit_path or AUDIT_LOG_PATH

    try:
        ensure_data_dirs()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError as exc:
        # A failed audit write must never interrupt the main workflow.
        logger.warning("Audit log write failed for action=%s instrument=%s: %s", action, instrument, exc)
