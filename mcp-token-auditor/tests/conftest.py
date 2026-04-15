# Test fixtures and utilities

import pytest
from src.utils.encodings import TokenCounter
from src.models.audit import AuditEvent, TokenBreakdown, Alert
from src.storage.database import AuditDatabase
import tempfile
import os


@pytest.fixture
def token_counter():
    """Fixture: TokenCounter instance."""
    return TokenCounter(encoding_name="o200k_base")


@pytest.fixture
def temp_db():
    """Fixture: Temporary SQLite database."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = AuditDatabase(path)
    yield db
    db.close()
    os.unlink(path)


@pytest.fixture
def sample_tool_metadata():
    """Fixture: Sample tool metadata."""
    return {
        "name": "list_files",
        "description": "List all files in a directory. This tool recursively lists files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path"},
            },
            "required": ["path"]
        }
    }


@pytest.fixture
def sample_audit_payload():
    """Fixture: Sample audit payload from Proxy Intercept Agent."""
    return {
        "audit_id": "test-audit-123",
        "timestamp_ingress": "2025-03-25T14:32:01.482310Z",
        "timestamp_egress": "2025-03-25T14:32:01.485310Z",
        "server_id": "filesystem-server",
        "transport": "sse",
        "message_type": "tools/list",
        "raw_metadata": {
            "name": "list_files",
            "description": "List all files in a directory",
            "input_schema": {"type": "object"}
        }
    }
