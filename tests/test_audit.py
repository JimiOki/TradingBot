"""Tests for the audit log module (REQ-OPS-001)."""
import json
from pathlib import Path

import pytest

from trading_lab.audit import AuditAction, log_event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_entries(path: Path) -> list[dict]:
    """Read all JSON-lines entries from the audit log."""
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# REQ-OPS-001: entry structure
# ---------------------------------------------------------------------------

def test_log_event_writes_required_fields(tmp_path):
    """Every audit entry must contain timestamp, instrument, action, and values."""
    log_path = tmp_path / "audit.log"
    log_event(
        AuditAction.SIGNAL_GENERATED,
        instrument="GC=F",
        values={"signal": 1, "close": 1950.0},
        audit_path=log_path,
    )

    entries = read_entries(log_path)
    assert len(entries) == 1
    entry = entries[0]

    assert "timestamp" in entry
    assert entry["instrument"] == "GC=F"
    assert entry["action"] == AuditAction.SIGNAL_GENERATED
    assert entry["values"]["signal"] == 1
    assert entry["values"]["close"] == 1950.0


def test_timestamp_is_iso8601_utc(tmp_path):
    """Timestamp must be an ISO 8601 UTC string (ends with +00:00 or Z)."""
    log_path = tmp_path / "audit.log"
    log_event(AuditAction.LLM_CALL_MADE, instrument="CL=F", values={}, audit_path=log_path)

    entry = read_entries(log_path)[0]
    ts = entry["timestamp"]
    assert "+00:00" in ts or ts.endswith("Z"), f"Timestamp not UTC: {ts}"


# ---------------------------------------------------------------------------
# REQ-OPS-001: append-only, never truncated
# ---------------------------------------------------------------------------

def test_second_call_appends_not_overwrites(tmp_path):
    """A second log_event call appends a new line; the first entry is still present."""
    log_path = tmp_path / "audit.log"
    log_event(AuditAction.SIGNAL_GENERATED, instrument="GC=F", values={"signal": 1}, audit_path=log_path)
    log_event(AuditAction.SIGNAL_GENERATED, instrument="SI=F", values={"signal": -1}, audit_path=log_path)

    entries = read_entries(log_path)
    assert len(entries) == 2
    assert entries[0]["instrument"] == "GC=F"
    assert entries[1]["instrument"] == "SI=F"


def test_all_action_types_accepted(tmp_path):
    """All six AuditAction constants are accepted without error."""
    log_path = tmp_path / "audit.log"
    actions = [
        AuditAction.SIGNAL_GENERATED,
        AuditAction.SIGNAL_APPROVED,
        AuditAction.SIGNAL_REJECTED,
        AuditAction.LLM_CALL_MADE,
        AuditAction.LLM_CALL_CACHED,
        AuditAction.LLM_CALL_FAILED,
    ]
    for action in actions:
        log_event(action, instrument="HG=F", values={}, audit_path=log_path)

    entries = read_entries(log_path)
    assert len(entries) == len(actions)
    recorded_actions = [e["action"] for e in entries]
    assert recorded_actions == actions


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_unknown_action_raises_value_error(tmp_path):
    """An unrecognised action string raises ValueError before writing anything."""
    log_path = tmp_path / "audit.log"
    with pytest.raises(ValueError, match="Unknown audit action"):
        log_event("trade_placed", instrument="GC=F", values={}, audit_path=log_path)
    assert not log_path.exists()


def test_empty_instrument_raises_value_error(tmp_path):
    """An empty instrument string raises ValueError."""
    log_path = tmp_path / "audit.log"
    with pytest.raises(ValueError, match="instrument"):
        log_event(AuditAction.SIGNAL_GENERATED, instrument="", values={}, audit_path=log_path)


# ---------------------------------------------------------------------------
# REQ-OPS-001: signal_generated entry has correct fields
# ---------------------------------------------------------------------------

def test_signal_generated_entry_fields(tmp_path):
    """A signal_generated event has correct action, non-null instrument and timestamp."""
    log_path = tmp_path / "audit.log"
    log_event(
        AuditAction.SIGNAL_GENERATED,
        instrument="NG=F",
        values={"signal": 0, "close": 2.45, "confidence_score": 50},
        audit_path=log_path,
    )
    entry = read_entries(log_path)[0]
    assert entry["action"] == "signal_generated"
    assert entry["instrument"] is not None and entry["instrument"] != ""
    assert entry["timestamp"] is not None and entry["timestamp"] != ""
