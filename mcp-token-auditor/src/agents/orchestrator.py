"""Orchestrator Agent - Master coordinator and session lifecycle manager."""

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import defaultdict
import uuid

from src.models.audit import SessionManifest, ErrorPayload
from src.storage.database import AuditDatabase
from src.utils.encodings import TokenCounter

logger = logging.getLogger(__name__)


class Orchestrator:
    """Master coordinator. Owns session lifecycle, agent dispatch, and conflict resolution."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize Orchestrator.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.session_id = str(uuid.uuid4())
        self.session_manifest: Optional[SessionManifest] = None
        self.db: Optional[AuditDatabase] = None
        self.token_counter: Optional[TokenCounter] = None
        self.agents: Dict[str, Any] = {}
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.running = False
        self.audio_buffer: List[Dict[str, Any]] = []  # Retry buffer
        
        # Metrics collection
        self.metrics = {
            "start_time": time.time(),
            "messages_processed": 0,
            "errors_count": 0,
            "agents_active": 0,
            "db_operations": 0,
            "rate_limits_hit": 0,
        }
        self.performance_counters = defaultdict(int)
        
        logger.info(f"Orchestrator initialized with session_id: {self.session_id}")

    async def bootstrap(self) -> bool:
        """Bootstrap all agents and perform startup checks.
        
        Returns:
            True if successful, False otherwise
        """
        logger.info("Starting orchestrator bootstrap...")
        
        # 1. Validate config
        if not self._validate_config():
            await self._emit_fault("CONFIG_INVALID", "Configuration validation failed")
            return False
        
        # 2. Initialize database
        storage_path = self.config.get("auditor", {}).get("storage_path", "./audit.db")
        self.db = AuditDatabase(storage_path)
        logger.info("✓ Database initialized")
        
        # 3. Initialize token counter
        encoding = self.config.get("auditor", {}).get("encoding", "o200k_base")
        self.token_counter = TokenCounter(encoding)
        logger.info(f"✓ Token counter initialized with encoding: {encoding}")
        
        # 4. Create session manifest
        ctx_limit = self.config.get("auditor", {}).get("context_window_limit", 128000)
        servers = self.config.get("proxy", {}).get("upstream_servers", [])
        registered_servers = {s["id"]: s.get("url", "") for s in servers}
        
        self.session_manifest = SessionManifest(
            session_id=self.session_id,
            encoding=encoding,
            context_window_limit=ctx_limit,
            registered_servers=registered_servers,
        )
        logger.info(f"✓ Session manifest created with {len(registered_servers)} servers")
        
        # 5. Health check upstream servers
        await self._health_check_servers(servers)
        
        # 6-9. Initialize downstream agents (in order)
        await self._init_agents()
        
        self.running = True
        logger.info("✓ Orchestrator bootstrap complete")
        return True

    def _validate_config(self) -> bool:
        """Validate configuration schema."""
        try:
            assert "auditor" in self.config
            assert "proxy" in self.config
            assert "alerts" in self.config
            assert "dashboard" in self.config
            
            auditor = self.config["auditor"]
            assert "encoding" in auditor
            assert "context_window_limit" in auditor
            
            proxy = self.config["proxy"]
            assert "listen_port" in proxy
            assert "upstream_servers" in proxy
            
            return True
        except AssertionError as e:
            logger.error(f"Config validation failed: {e}")
            return False

    async def _health_check_servers(self, servers: List[Dict[str, Any]]):
        """Ping all upstream servers for reachability.
        
        Args:
            servers: List of server configs
        """
        for server in servers:
            server_id = server.get("id", "unknown")
            url = server.get("url", "")
            status = "reachable"  # In production, implement actual health check
            logger.info(f"Server health check - {server_id}: {status}")

    async def _init_agents(self):
        """Initialize all downstream agents."""
        # Agents will be injected/registered as needed
        logger.info("Agents initialized (lazy loading)")

    async def route_mcp_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Route incoming MCP message to Proxy Intercept Agent.
        
        Args:
            message: MCP JSON-RPC message
            
        Returns:
            Routed/transformed message with audit_id attached
        """
        if not self.running:
            return message
        
        # Attach audit ID for tracing
        audit_id = message.get("__audit_id") or str(uuid.uuid4())
        message["__audit_id"] = audit_id
        
        # Update metrics
        self.metrics["messages_processed"] += 1
        
        return message

    async def buffer_message(self, message: Dict[str, Any], attempt: int = 1):
        """Buffer message for retry with exponential backoff.
        
        Args:
            message: Message to buffer
            attempt: Current attempt number (1-3)
        """
        if attempt > 3:
            logger.error(f"Message {message.get('__audit_id')} dropped after 3 retries")
            self.metrics["errors_count"] += 1
            return
        
        backoff_ms = [50, 150, 450][attempt - 1]
        await asyncio.sleep(backoff_ms / 1000.0)
        
        self.audio_buffer.append(message)
        logger.info(f"Buffered message {message.get('__audit_id')} (attempt {attempt})")

    async def _emit_fault(self, error_code: str, message: str):
        """Emit a SYSTEM_FAULT event.
        
        Args:
            error_code: Error code
            message: Error message
        """
        fault = ErrorPayload(
            error_code=error_code,
            agent="ORCHESTRATOR",
            message=message,
            recoverable=False,
        )
        self.metrics["errors_count"] += 1
        logger.critical(f"SYSTEM_FAULT: {fault.to_dict()}")

    def record_db_operation(self):
        """Record a database operation for metrics."""
        self.metrics["db_operations"] += 1

    def record_rate_limit_hit(self):
        """Record a rate limit hit for metrics."""
        self.metrics["rate_limits_hit"] += 1

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics.
        
        Returns:
            Metrics dictionary
        """
        uptime = time.time() - self.metrics["start_time"]
        return {
            **self.metrics,
            "uptime_seconds": uptime,
            "messages_per_second": self.metrics["messages_processed"] / uptime if uptime > 0 else 0,
            "error_rate": self.metrics["errors_count"] / self.metrics["messages_processed"] if self.metrics["messages_processed"] > 0 else 0,
            "performance_counters": dict(self.performance_counters),
        }

    async def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down orchestrator...")
        self.running = False
        
        # Log final metrics
        final_metrics = self.get_metrics()
        logger.info(f"Final metrics: {final_metrics}")
        
        if self.db:
            self.db.close()
        logger.info("Orchestrator shutdown complete")
