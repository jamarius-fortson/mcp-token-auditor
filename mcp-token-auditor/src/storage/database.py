"""Database storage layer for audit logs with connection pooling."""

import sqlite3
import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class AuditDatabase:
    """SQLite-based audit log storage with connection pooling."""

    def __init__(self, db_path: str = "./audit.db"):
        """Initialize database with connection pooling.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._connections: Dict[int, sqlite3.Connection] = {}

        # Initialize schema on first connection
        with self._get_connection() as conn:
            self._init_schema(conn)

        logger.info(f"AuditDatabase initialized with path: {self.db_path}")

    @contextmanager
    def _get_connection(self):
        """Get a thread-local database connection."""
        thread_id = threading.get_ident()

        with self._lock:
            if thread_id not in self._connections:
                conn = sqlite3.connect(
                    str(self.db_path),
                    check_same_thread=False,  # Allow cross-thread usage with locking
                    timeout=30.0,  # 30 second timeout for locks
                )
                conn.row_factory = sqlite3.Row
                self._connections[thread_id] = conn
            conn = self._connections[thread_id]

        try:
            yield conn
        except Exception as e:
            logger.error(f"Database operation failed: {e}")
            conn.rollback()
            raise

    def _init_schema(self, conn: sqlite3.Connection):
        """Initialize database schema."""
        cursor = conn.cursor()

        # Audit events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                audit_id TEXT UNIQUE NOT NULL,
                timestamp_ingress TEXT NOT NULL,
                timestamp_egress TEXT,
                server_id TEXT NOT NULL,
                transport TEXT NOT NULL,
                message_type TEXT NOT NULL,
                tool_name TEXT,
                token_breakdown TEXT,
                session_cumulative_tokens INTEGER,
                context_window_limit INTEGER,
                encoding_used TEXT,
                raw_metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Per-server token counters
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS server_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                server_id TEXT NOT NULL,
                tool_name TEXT,
                total_tokens INTEGER,
                call_count INTEGER DEFAULT 1,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(session_id, server_id, tool_name)
            )
        """)

        # Alerts
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id TEXT UNIQUE NOT NULL,
                rule_id TEXT NOT NULL,
                severity TEXT NOT NULL,
                triggered_by_audit_id TEXT,
                server_id TEXT,
                tool_name TEXT,
                message TEXT,
                current_value REAL,
                threshold_value REAL,
                timestamp TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Alert state (for debouncing)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alert_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id TEXT NOT NULL,
                server_id TEXT NOT NULL,
                last_fired TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(rule_id, server_id)
            )
        """)

        # Create indices for performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_server ON audit_events(server_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_tool ON audit_events(tool_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp_ingress)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_rule ON alerts(rule_id)")

        conn.commit()
        logger.info("Database schema initialized")

    def write_audit_event(self, event_dict: Dict[str, Any]) -> bool:
        """Write an audit event to storage (append-only).

        Args:
            event_dict: Audit event as dictionary

        Returns:
            True if successful, False otherwise
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO audit_events (
                        audit_id, timestamp_ingress, timestamp_egress,
                        server_id, transport, message_type, tool_name,
                        token_breakdown, session_cumulative_tokens,
                        context_window_limit, encoding_used, raw_metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event_dict["audit_id"],
                    event_dict["timestamp_ingress"],
                    event_dict.get("timestamp_egress"),
                    event_dict["server_id"],
                    event_dict["transport"],
                    event_dict["message_type"],
                    event_dict.get("tool_name"),
                    json.dumps(event_dict.get("token_breakdown")),
                    event_dict["session_cumulative_tokens"],
                    event_dict["context_window_limit"],
                    event_dict["encoding_used"],
                    json.dumps(event_dict.get("raw_metadata")),
                ))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to write audit event: {e}")
            return False

    def write_alert(self, alert_dict: Dict[str, Any]) -> bool:
        """Write an alert to storage.

        Args:
            alert_dict: Alert as dictionary

        Returns:
            True if successful, False otherwise
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO alerts (
                        alert_id, rule_id, severity, triggered_by_audit_id,
                        server_id, tool_name, message, current_value,
                        threshold_value, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    alert_dict["alert_id"],
                    alert_dict["rule_id"],
                    alert_dict["severity"],
                    alert_dict["triggered_by_audit_id"],
                    alert_dict.get("server_id"),
                    alert_dict.get("tool_name"),
                    alert_dict["message"],
                    alert_dict.get("current_value"),
                    alert_dict.get("threshold_value"),
                    alert_dict["timestamp"],
                ))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to write alert: {e}")
            return False

    def update_alert_state(self, rule_id: str, server_id: str) -> bool:
        """Update alert state for debouncing (upsert).

        Args:
            rule_id: Alert rule ID
            server_id: Server ID

        Returns:
            True if successful
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO alert_state (rule_id, server_id, last_fired)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (rule_id, server_id))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update alert state: {e}")
            return False

    def get_alert_last_fired(self, rule_id: str, server_id: str) -> Optional[datetime]:
        """Get last fired timestamp for an alert rule on a server.

        Args:
            rule_id: Alert rule ID
            server_id: Server ID

        Returns:
            Last fired datetime or None
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT last_fired FROM alert_state
                    WHERE rule_id = ? AND server_id = ?
                """, (rule_id, server_id))
                row = cursor.fetchone()
                if row:
                    return datetime.fromisoformat(row["last_fired"])
                return None
        except Exception as e:
            logger.error(f"Failed to get alert state: {e}")
            return None

    def get_session_token_summary(self, server_id: str) -> Dict[str, int]:
        """Get token summary for a server in current session.

        Args:
            server_id: Server ID

        Returns:
            Dict with total_tokens, tool_count
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT SUM(json_extract(token_breakdown, '$.total_tool_tokens')) as total, COUNT(*) as count
                    FROM audit_events
                    WHERE server_id = ?
                """, (server_id,))
                row = cursor.fetchone()
                return {
                    "total_tokens": row["total"] or 0,
                    "event_count": row["count"] or 0,
                }
        except Exception as e:
            logger.error(f"Failed to get token summary: {e}")
            return {"total_tokens": 0, "event_count": 0}

    def get_call_count(self, server_id: str, minutes: int = 1) -> int:
        """Get call count for a server in the last N minutes.

        Args:
            server_id: Server ID
            minutes: Time window in minutes

        Returns:
            Number of calls
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                limit = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
                cursor.execute("""
                    SELECT COUNT(*) as count FROM audit_events
                    WHERE server_id = ? AND timestamp_ingress > ?
                """, (server_id, limit))
                row = cursor.fetchone()
                return row["count"] or 0
        except Exception as e:
            logger.error(f"Failed to get call count: {e}")
            return 0

    def get_server_token_average(self, server_id: str) -> float:
        """Get average token count per call for a server.

        Args:
            server_id: Server ID

        Returns:
            Average token count
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT AVG(json_extract(token_breakdown, '$.total_tool_tokens')) as avg_tokens
                    FROM audit_events
                    WHERE server_id = ? AND tool_name IS NOT NULL
                """, (server_id,))
                row = cursor.fetchone()
                return float(row["avg_tokens"] or 0.0)
        except Exception as e:
            logger.error(f"Failed to get token average: {e}")
            return 0.0

    def get_similar_tools(self, description: str) -> List[Dict[str, Any]]:
        """Find tools with similar descriptions.

        Args:
            description: Description string to compare

        Returns:
            List of similar tools
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                words = description.split()[:2]
                if not words:
                    return []
                # Use simple prefix matching on description words for SQLite
                pattern = f"%{'%'.join(words)}%"
                cursor.execute("""
                    SELECT DISTINCT server_id, tool_name, 
                           json_extract(raw_metadata, '$.description') as desc
                    FROM audit_events
                    WHERE desc LIKE ? AND tool_name IS NOT NULL
                    LIMIT 3
                """, (pattern,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to find similar tools: {e}")
            return []

    def get_rolling_24h_average(self, server_id: str) -> float:
        """Get average token count per call for a server in the last 24 hours.

        Args:
            server_id: Server ID

        Returns:
            Average token count
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                limit = (datetime.utcnow() - timedelta(hours=24)).isoformat()
                cursor.execute("""
                    SELECT AVG(json_extract(token_breakdown, '$.total_tool_tokens')) as avg_tokens
                    FROM audit_events
                    WHERE server_id = ? AND timestamp_ingress > ? AND tool_name IS NOT NULL
                """, (server_id, limit))
                row = cursor.fetchone()
                return float(row["avg_tokens"] or 0.0)
        except Exception as e:
            logger.error(f"Failed to get rolling 24h average: {e}")
            return 0.0

    def close(self):
        """Close all database connections."""
        with self._lock:
            for conn in self._connections.values():
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
            self._connections.clear()
        logger.info("Database connections closed")
