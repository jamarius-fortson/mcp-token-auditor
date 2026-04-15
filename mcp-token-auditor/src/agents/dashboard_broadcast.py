"""Dashboard Broadcast Agent - Real-time WebSocket data layer for React dashboard."""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Set
from datetime import datetime

logger = logging.getLogger(__name__)


class DashboardBroadcastAgent:
    """Real-time WebSocket data layer for dashboard. Single source of truth for UI state."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize dashboard broadcast agent.
        
        Args:
            config: Dashboard configuration
        """
        self.config = config
        self.websocket_port = config.get("dashboard", {}).get("websocket_port", 8766)
        self.cors_origins = config.get("dashboard", {}).get("cors_origins", [])
        
        self.connected_clients: Set[str] = set()  # Client session IDs
        self.event_buffer: List[Dict[str, Any]] = []
        self.session_state: Dict[str, Any] = {}
        self.max_buffer_size = 1000
        
        logger.info(f"DashboardBroadcastAgent initialized on port {self.websocket_port}")

    async def register_client(self, client_id: str) -> Dict[str, Any]:
        """Register a new dashboard client.
        
        Args:
            client_id: Client session ID
            
        Returns:
            Initial session state payload for hydration
        """
        self.connected_clients.add(client_id)
        logger.info(f"Client registered: {client_id} ({len(self.connected_clients)} total)")
        
        return {
            "type": "SESSION_INIT",
            "event_type": "SESSION_INIT",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "state": self.session_state,
            "buffered_events": self.event_buffer[-100:],  # Last 100 events
        }

    async def unregister_client(self, client_id: str):
        """Unregister a dashboard client.
        
        Args:
            client_id: Client session ID
        """
        self.connected_clients.discard(client_id)
        logger.info(f"Client unregistered: {client_id} ({len(self.connected_clients)} total)")

    async def broadcast_audit_event(self, audit_event: Dict[str, Any]):
        """Broadcast token audit event to all connected clients.
        
        Args:
            audit_event: Audit event from Token Audit Agent
        """
        event = {
            "event_type": "TOKEN_AUDIT_EVENT",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": audit_event,
        }
        
        await self._queue_and_broadcast(event)
        
        # Update session state
        self.session_state["last_audit_event"] = audit_event
        self.session_state["last_event_timestamp"] = event["timestamp"]

    async def broadcast_alert(self, alert: Dict[str, Any]):
        """Broadcast alert to all connected clients.
        
        Args:
            alert: Alert from Alert Monitor Agent
        """
        event = {
            "event_type": "ALERT_FIRED",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": alert,
        }
        
        await self._queue_and_broadcast(event)
        
        # Update session state
        if "recent_alerts" not in self.session_state:
            self.session_state["recent_alerts"] = []
        
        self.session_state["recent_alerts"].insert(0, alert)
        self.session_state["recent_alerts"] = self.session_state["recent_alerts"][:20]  # Keep last 20

    async def broadcast_compression_suggestion(self, suggestion: Dict[str, Any]):
        """Broadcast compression suggestion to all connected clients.
        
        Args:
            suggestion: Suggestion from Compression Advisor Agent
        """
        event = {
            "event_type": "COMPRESSION_SUGGESTION",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": suggestion,
        }
        
        await self._queue_and_broadcast(event)
        
        # Update session state
        if "compression_suggestions" not in self.session_state:
            self.session_state["compression_suggestions"] = []
        
        self.session_state["compression_suggestions"].insert(0, suggestion)
        self.session_state["compression_suggestions"] = self.session_state["compression_suggestions"][:50]

    async def broadcast_session_summary(self, summary: Dict[str, Any]):
        """Broadcast session summary.
        
        Args:
            summary: Session summary from Token Audit Agent
        """
        event = {
            "event_type": "SESSION_SUMMARY",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": summary,
        }
        
        await self._queue_and_broadcast(event)
        self.session_state["summary"] = summary

    async def broadcast_system_fault(self, fault: Dict[str, Any]):
        """Broadcast system fault to all clients.
        
        Args:
            fault: Error/fault payload
        """
        event = {
            "event_type": "SYSTEM_FAULT",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": fault,
        }
        
        await self._queue_and_broadcast(event)
        self.session_state["system_fault"] = fault

    async def broadcast_latency_breach(self, breach_info: Dict[str, Any]):
        """Broadcast latency breach warning.
        
        Args:
            breach_info: Latency breach details
        """
        event = {
            "event_type": "LATENCY_BREACH",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": breach_info,
        }
        
        await self._queue_and_broadcast(event)

    async def _queue_and_broadcast(self, event: Dict[str, Any]):
        """Queue event and broadcast to connected clients.
        
        Args:
            event: Event to broadcast
        """
        # Buffer event (ring buffer)
        self.event_buffer.append(event)
        if len(self.event_buffer) > self.max_buffer_size:
            self.event_buffer.pop(0)
        
        # Broadcast to all connected clients
        if self.connected_clients:
            logger.debug(
                f"Broadcasting {event['event_type']} to {len(self.connected_clients)} clients"
            )
            # In production, send via WebSocket to each client
            # For now, this is async-ready but mock
            await asyncio.sleep(0)
        else:
            logger.debug(f"No connected clients, buffering {event['event_type']}")

    async def get_session_summary_rest(self) -> Dict[str, Any]:
        """Get session summary for REST API (GET /api/v1/session/summary).
        
        Returns:
            Session summary dict
        """
        return {
            "connected_clients": len(self.connected_clients),
            "event_buffer_size": len(self.event_buffer),
            "session_state": self.session_state,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
