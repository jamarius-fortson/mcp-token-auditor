"""Audit data models for token tracking and attribution."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
import uuid


class MessageType(str, Enum):
    """MCP message types."""
    TOOLS_LIST = "tools/list"
    TOOLS_CALL = "tools/call"
    OTHER = "other"


class TransportType(str, Enum):
    """Supported transport mechanisms."""
    WEBSOCKET = "websocket"
    SSE = "sse"
    STDIO = "stdio"


@dataclass
class TokenBreakdown:
    """Detailed token count breakdown for a tool."""
    name_tokens: int
    description_tokens: int
    schema_tokens: int
    total_tool_tokens: int

    def to_dict(self) -> Dict[str, int]:
        return asdict(self)


@dataclass
class AuditEvent:
    """Core audit event emitted by Token Audit Agent."""
    audit_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp_ingress: datetime = field(default_factory=datetime.utcnow)
    timestamp_egress: Optional[datetime] = None
    server_id: str = ""
    transport: TransportType = TransportType.WEBSOCKET
    message_type: MessageType = MessageType.OTHER
    tool_name: str = ""
    
    # Metadata from MCP
    raw_metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Token accounting
    token_breakdown: Optional[TokenBreakdown] = None
    session_cumulative_tokens: int = 0
    context_window_limit: int = 128000
    rolling_24h_average: float = 0.0
    encoding_used: str = "o200k_base"

    @property
    def context_window_pct(self) -> float:
        """Calculate context window percentage."""
        if self.context_window_limit == 0:
            return 0.0
        pct = (self.session_cumulative_tokens / self.context_window_limit) * 100
        return round(pct, 2)

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "audit_id": self.audit_id,
            "timestamp_ingress": self.timestamp_ingress.isoformat() + "Z",
            "timestamp_egress": self.timestamp_egress.isoformat() + "Z" if self.timestamp_egress else None,
            "server_id": self.server_id,
            "transport": self.transport.value,
            "message_type": self.message_type.value,
            "tool_name": self.tool_name,
            "raw_metadata": self.raw_metadata,
            "token_breakdown": self.token_breakdown.to_dict() if self.token_breakdown else None,
            "session_cumulative_tokens": self.session_cumulative_tokens,
            "context_window_limit": self.context_window_limit,
            "context_window_pct": self.context_window_pct,
            "rolling_24h_average": self.rolling_24h_average,
            "encoding_used": self.encoding_used,
        }
        return data


@dataclass
class CompressionSuggestion:
    """Suggested compression for a tool's descriptions."""
    tool_name: str
    server_id: str
    heuristic: str  # cloudflare_code_mode | redundancy | schema_bloat | deduplication
    original_text: str
    suggested_text: str
    current_tokens: int
    token_delta: int  # negative = savings
    confidence: float  # 0.0 - 1.0
    apply_automatically: bool = False

    @property
    def projected_tokens(self) -> int:
        return self.current_tokens + self.token_delta

    def to_dict(self) -> Dict[str, Any]:
        return {
            "heuristic": self.heuristic,
            "original_text": self.original_text,
            "suggested_text": self.suggested_text,
            "token_delta": self.token_delta,
            "projected_tokens": self.projected_tokens,
            "confidence": round(self.confidence, 2),
            "apply_automatically": self.apply_automatically,
        }


@dataclass
class AlertRule:
    """Configurable alert rule."""
    rule_id: str
    trigger: str
    threshold: float
    severity: str  # WARNING | CRITICAL | INFO
    enabled: bool = True


@dataclass
class Alert:
    """Alert event emitted by Alert Monitor Agent."""
    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    rule_id: str = ""
    severity: str = "WARNING"
    triggered_by_audit_id: str = ""
    server_id: str = ""
    tool_name: Optional[str] = None
    message: str = ""
    current_value: float = 0.0
    threshold_value: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    suppressed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "triggered_by_audit_id": self.triggered_by_audit_id,
            "server_id": self.server_id,
            "tool_name": self.tool_name,
            "message": self.message,
            "current_value": round(self.current_value, 2),
            "threshold_value": round(self.threshold_value, 2),
            "timestamp": self.timestamp.isoformat() + "Z",
            "suppressed": self.suppressed,
        }


@dataclass
class ErrorPayload:
    """Standardized error response."""
    error_code: str
    agent: str
    audit_id: Optional[str] = None
    message: str = ""
    recoverable: bool = True
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_code": self.error_code,
            "agent": self.agent,
            "audit_id": self.audit_id,
            "message": self.message,
            "recoverable": self.recoverable,
            "timestamp": self.timestamp.isoformat() + "Z",
        }


@dataclass
class SessionManifest:
    """Session initialization manifest."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    encoding: str = "o200k_base"
    context_window_limit: int = 128000
    registered_servers: Dict[str, str] = field(default_factory=dict)  # server_id -> url/identifier
    timestamp_start: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "encoding": self.encoding,
            "context_window_limit": self.context_window_limit,
            "registered_servers": self.registered_servers,
            "timestamp_start": self.timestamp_start.isoformat() + "Z",
        }
