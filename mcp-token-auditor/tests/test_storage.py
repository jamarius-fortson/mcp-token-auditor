# Tests for database storage

import pytest
from src.storage.database import AuditDatabase
import json


def test_database_init(temp_db):
    """Test database initialization."""
    assert temp_db.conn is not None


def test_write_audit_event(temp_db, sample_audit_payload):
    """Test writing an audit event."""
    result = temp_db.write_audit_event(sample_audit_payload)
    assert result is True


def test_write_alert(temp_db):
    """Test writing an alert."""
    alert = {
        "alert_id": "test-alert-123",
        "rule_id": "CTX_WARN",
        "severity": "WARNING",
        "triggered_by_audit_id": "test-audit-123",
        "server_id": "test-server",
        "tool_name": "test_tool",
        "message": "Test alert message",
        "current_value": 45.5,
        "threshold_value": 40.0,
        "timestamp": "2025-03-25T14:32:01.482310Z",
    }
    result = temp_db.write_alert(alert)
    assert result is True


def test_get_session_token_summary(temp_db, sample_audit_payload):
    """Test retrieving session token summary."""
    temp_db.write_audit_event(sample_audit_payload)
    summary = temp_db.get_session_token_summary("filesystem-server")
    assert "total_tokens" in summary
    assert "event_count" in summary


def test_update_alert_state(temp_db):
    """Test updating alert debounce state."""
    result = temp_db.update_alert_state("CTX_WARN", "test-server")
    assert result is True


def test_get_alert_last_fired(temp_db):
    """Test retrieving last fired time for alert."""
    temp_db.update_alert_state("CTX_WARN", "test-server")
    last_fired = temp_db.get_alert_last_fired("CTX_WARN", "test-server")
    assert last_fired is not None
