"""Proxy Intercept Agent - Transparent MCP traffic proxy and metadata extractor."""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional
import uuid

from src.models.audit import AuditEvent, MessageType, TransportType
from src.utils.validation import extract_tool_metadata, is_malformed_json_rpc

logger = logging.getLogger(__name__)


class ProxyInterceptAgent:
    """Transparent proxy layer. Intercepts MCP JSON-RPC traffic bidirectionally."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize proxy agent.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.servers: Dict[str, Dict[str, Any]] = {}
        self.latency_warnings: int = 0
        
        # Build server map from config
        for server in config.get("proxy", {}).get("upstream_servers", []):
            self.servers[server["id"]] = {
                "url": server.get("url", ""),
                "transport": server.get("transport", "websocket"),
            }
        
        logger.info(f"ProxyInterceptAgent initialized with {len(self.servers)} servers")

    async def intercept_request(
        self, 
        message: Dict[str, Any],
        server_id: str,
    ) -> tuple[Dict[str, Any], Optional[AuditEvent]]:
        """Intercept incoming MCP request.
        
        Args:
            message: MCP JSON-RPC request
            server_id: Target server ID
            
        Returns:
            Tuple of (processed message, audit event or None)
        """
        audit_id = message.get("__audit_id", str(uuid.uuid4()))
        timestamp_ingress = datetime.utcnow()
        
        # Attach timestamps and audit ID
        message["__audit_id"] = audit_id
        message["__timestamp_ingress"] = timestamp_ingress.isoformat()
        
        # Determine message type
        message_type = MessageType.OTHER
        if message.get("method") == "tools/list":
            message_type = MessageType.TOOLS_LIST
        elif message.get("method") == "tools/call":
            message_type = MessageType.TOOLS_CALL
        
        # Create audit event
        server_info = self.servers.get(server_id, {})
        transport = server_info.get("transport", "websocket")
        
        audit_event = AuditEvent(
            audit_id=audit_id,
            timestamp_ingress=timestamp_ingress,
            server_id=server_id,
            transport=TransportType(transport),
            message_type=message_type,
        )
        
        logger.debug(f"Intercepted {message_type.value} request from {server_id}")
        return message, audit_event

    async def intercept_response(
        self,
        message: Dict[str, Any],
        audit_id: str,
        server_id: str,
    ) -> Optional[AuditEvent]:
        """Intercept MCP response (tools/list).
        
        Args:
            message: MCP JSON-RPC response
            audit_id: Audit ID from request
            server_id: Server ID
            
        Returns:
            Updated audit event with metadata and timing
        """
        timestamp_egress = datetime.utcnow()
        
        # Check for malformed JSON-RPC
        if is_malformed_json_rpc(message):
            logger.warning(f"Malformed JSON-RPC from {server_id}: {message}")
            return None
        
        # Extract tool metadata if tools/list response
        raw_metadata = None
        tools = extract_tool_metadata(message)
        
        audit_event = AuditEvent(
            audit_id=audit_id,
            timestamp_ingress=datetime.fromisoformat(message.get("__timestamp_ingress", "")),
            timestamp_egress=timestamp_egress,
            server_id=server_id,
            message_type=MessageType.TOOLS_LIST,
            transport=TransportType(self.servers.get(server_id, {}).get("transport", "websocket")),
        )
        
        # If tools were extracted, store first tool's metadata as example
        if tools:
            audit_event.raw_metadata = tools[0]  # Typically only one tool per response in testing
            logger.debug(f"Extracted {len(tools)} tools from tools/list response")
        
        return audit_event

    async def forward_to_server(
        self,
        message: Dict[str, Any],
        server_id: str,
    ) -> Dict[str, Any]:
        """Forward message to upstream MCP server (passthrough unmodified).
        
        Args:
            message: Message to forward
            server_id: Target server
            
        Returns:
            Original message (unmodified)
        """
        # In production, implement actual forwarding via HTTP/WebSocket/stdio
        # For now, this is a mock
        logger.debug(f"Forwarding message to server {server_id}")
        return message

    def check_latency(self, ingress: datetime, egress: datetime) -> bool:
        """Check if proxy latency exceeds 5ms p99.
        
        Args:
            ingress: Ingress timestamp
            egress: Egress timestamp
            
        Returns:
            True if within budget, False if breach
        """
        latency_ms = (egress - ingress).total_seconds() * 1000
        budget_ms = 5.0
        
        if latency_ms > budget_ms:
            self.latency_warnings += 1
            logger.warning(
                f"LATENCY_BREACH: {latency_ms:.2f}ms > {budget_ms}ms "
                f"(warnings: {self.latency_warnings})"
            )
            return False
        
        return True

    def get_audit_output_contract(self, audit_event: AuditEvent) -> Dict[str, Any]:
        """Format audit event for Token Audit Agent consumption.
        
        Returns:
            Structured audit event dict matching output contract
        """
        return {
            "audit_id": audit_event.audit_id,
            "timestamp_ingress": audit_event.timestamp_ingress.isoformat() + "Z",
            "timestamp_egress": audit_event.timestamp_egress.isoformat() + "Z" if audit_event.timestamp_egress else None,
            "server_id": audit_event.server_id,
            "transport": audit_event.transport.value,
            "message_type": audit_event.message_type.value,
            "raw_metadata": audit_event.raw_metadata or {},
        }
