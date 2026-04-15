"""Token Audit Agent - Precision token counter and cost attributor."""

import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional
import json

from src.models.audit import AuditEvent, TokenBreakdown
from src.utils.encodings import TokenCounter
from src.storage.database import AuditDatabase

logger = logging.getLogger(__name__)


class TokenAuditAgent:
    """Precision token counter and cost attributor."""

    def __init__(
        self,
        token_counter: TokenCounter,
        db: AuditDatabase,
        context_window_limit: int = 128000,
    ):
        """Initialize token audit agent.
        
        Args:
            token_counter: TokenCounter instance
            db: AuditDatabase instance
            context_window_limit: Context window size in tokens
        """
        self.token_counter = token_counter
        self.db = db
        self.context_window_limit = context_window_limit
        
        # Thread-safe accumulators
        self._lock = asyncio.Lock()
        self._session_cumulative: int = 0
        self._server_tokens: Dict[str, int] = {}
        
        logger.info("TokenAuditAgent initialized")

    async def process_audit_payload(
        self,
        audit_payload: Dict[str, Any],
    ) -> Optional[AuditEvent]:
        """Process metadata from Proxy Intercept Agent and count tokens.
        
        Args:
            audit_payload: Audit event from proxy
            
        Returns:
            Enriched audit event with token counts, or None on error
        """
        server_id = audit_payload.get("server_id", "")
        raw_metadata = audit_payload.get("raw_metadata", {})
        
        # Validate server_id (check if registered)
        # In production, validate against session manifest
        
        # Extract tool metadata components
        tool_name = raw_metadata.get("name", "")
        description = raw_metadata.get("description", "")
        input_schema = raw_metadata.get("input_schema", {})
        
        # Count tokens with proper error handling
        try:
            token_counts = self.token_counter.count_tool_metadata(
                name=tool_name,
                description=description,
                schema=input_schema,
            )
        except ValueError as e:
            logger.error(f"Token counting failed for tool '{tool_name}' from {server_id}: {e}")
            # Don't return None - create event with zero counts but log the error
            token_counts = {
                "name_tokens": 0,
                "description_tokens": 0,
                "schema_tokens": 0,
                "total_tool_tokens": 0,
            }
        
        # Thread-safe update of accumulators
        total_tool_tokens = token_counts.get("total_tool_tokens", 0)
        await self._safe_update_tokens(server_id, total_tool_tokens)
        
        # Create enriched audit event
        audit_event = AuditEvent(
            audit_id=audit_payload["audit_id"],
            timestamp_ingress=datetime.fromisoformat(audit_payload["timestamp_ingress"].rstrip("Z")),
            timestamp_egress=datetime.fromisoformat(audit_payload["timestamp_egress"].rstrip("Z")) if audit_payload.get("timestamp_egress") else None,
            server_id=server_id,
            transport=audit_payload.get("transport", "websocket"),
            message_type=audit_payload.get("message_type", "other"),
            tool_name=tool_name,
            raw_metadata=raw_metadata,
            token_breakdown=TokenBreakdown(
                name_tokens=token_counts["name_tokens"],
                description_tokens=token_counts["description_tokens"],
                schema_tokens=token_counts["schema_tokens"],
                total_tool_tokens=token_counts["total_tool_tokens"],
            ),
            session_cumulative_tokens=self._session_cumulative,
            context_window_limit=self.context_window_limit,
            rolling_24h_average=self.db.get_rolling_24h_average(server_id),
            encoding_used=self.token_counter.encoding_name,
        )
        
        logger.info(
            f"Audited tool '{tool_name}' from {server_id}: "
            f"{total_tool_tokens} tokens, "
            f"session cumulative: {self._session_cumulative} ({audit_event.context_window_pct}%)"
        )
        
        # Persist to database
        if not self.db.write_audit_event(audit_event.to_dict()):
            logger.error(f"Failed to persist audit event {audit_event.audit_id}")
            return None
        
        return audit_event

    async def _safe_update_tokens(self, server_id: str, tokens: int):
        """Thread-safe update of token accumulators.
        
        Args:
            server_id: Server identifier
            tokens: Number of tokens to add
        """
        async with self._lock:
            self._session_cumulative += tokens
            if server_id not in self._server_tokens:
                self._server_tokens[server_id] = 0
            self._server_tokens[server_id] += tokens

    def get_session_summary(self) -> Dict[str, Any]:
        """Get session token summary.
        
        Returns:
            Summary dict with cumulative tokens, per-server breakdown, etc.
        """
        return {
            "session_cumulative_tokens": self._session_cumulative,
            "context_window_limit": self.context_window_limit,
            "context_window_pct": round(
                (self._session_cumulative / self.context_window_limit * 100) if self.context_window_limit > 0 else 0,
                2
            ),
            "server_tokens": self._server_tokens.copy(),  # Return copy for thread safety
            "encoding_used": self.token_counter.encoding_name,
        }
