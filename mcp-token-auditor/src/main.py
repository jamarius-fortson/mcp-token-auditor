"""Main FastAPI application for MCP Token Auditor."""

import asyncio
import logging
import json
import os
import secrets
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Depends, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import yaml

from src.agents.orchestrator import Orchestrator
from src.agents.proxy_intercept import ProxyInterceptAgent
from src.agents.token_audit import TokenAuditAgent
from src.agents.compression_advisor import CompressionAdvisorAgent
from src.agents.alert_monitor import AlertMonitorAgent
from src.agents.dashboard_broadcast import DashboardBroadcastAgent
from src.utils.validation import load_and_validate_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Security
security = HTTPBearer(auto_error=False)


class MCPTokenAuditorApp:
    """Main application orchestrating all agents."""

    def __init__(self, config_path: str = "config/config.yaml"):
        """Initialize the application.
        
        Args:
            config_path: Path to configuration file
        """
        self.config = self._load_config(config_path)
        self.app = FastAPI(
            title="MCP Token Auditor",
            version="1.0.0",
            docs_url="/docs" if self._is_development() else None,  # Disable docs in production
            redoc_url="/redoc" if self._is_development() else None,
        )
        self.orchestrator: Optional[Orchestrator] = None
        self.proxy_agent: Optional[ProxyInterceptAgent] = None
        self.token_audit_agent: Optional[TokenAuditAgent] = None
        self.compression_advisor: Optional[CompressionAdvisorAgent] = None
        self.alert_monitor: Optional[AlertMonitorAgent] = None
        self.dashboard_broadcast: Optional[DashboardBroadcastAgent] = None
        
        # Background task tracking to prevent garbage collection
        self.app.state.background_tasks = set()
        
        # Rate limiting (simple in-memory for now)
        self._rate_limits: Dict[str, Dict[str, Any]] = {}
        
        self._setup_middleware()
        self._setup_routes()

    def _is_development(self) -> bool:
        """Check if running in development mode."""
        return os.getenv("ENVIRONMENT", "development").lower() == "development"

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load and validate configuration from YAML file."""
        try:
            config = load_and_validate_config(config_path)
            logger.info(f"Configuration loaded and validated from {config_path}")
            return config.dict()
        except Exception as e:
            logger.error(f"Failed to load/validate config: {e}")
            return self._default_config()

    def _default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            "auditor": {
                "encoding": "o200k_base",
                "context_window_limit": 128000,
                "storage_backend": "sqlite",
                "storage_path": "./audit.db",
            },
            "proxy": {
                "listen_port": 8765,
                "upstream_servers": [],
            },
            "alerts": {
                "rules": {
                    "CTX_WARN": {"threshold": 40, "enabled": True},
                    "CTX_CRITICAL": {"threshold": 60, "enabled": True},
                    "TOOL_BLOAT": {"threshold": 300, "enabled": True},
                    "SCHEMA_BLOAT": {"threshold": 400, "enabled": True},
                    "CALL_SPIKE": {"threshold": 60, "enabled": True},
                    "SERVER_DRIFT": {"threshold": 25, "enabled": True},
                },
                "webhook_url": "",
            },
            "dashboard": {
                "websocket_port": 8766,
                "cors_origins": ["http://localhost:5173", "http://localhost:3000"],
            },
            "compression_advisor": {
                "min_confidence": 0.65,
                "min_description_tokens": 8,
                "enabled": True,
            },
            "security": {
                "api_key": os.getenv("MCP_AUDITOR_API_KEY", secrets.token_urlsafe(32)),
                "rate_limit_requests": 100,
                "rate_limit_window_seconds": 60,
            },
        }

    def _setup_middleware(self):
        """Setup CORS and other middleware."""
        cors_origins = self.config.get("dashboard", {}).get("cors_origins", [])
        if not cors_origins and self._is_development():
            cors_origins = ["*"]
        
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
            max_age=86400,
        )

    def _verify_api_key(self, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> bool:
        """Verify API key authentication."""
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        expected_key = self.config.get("security", {}).get("api_key", "")
        if not secrets.compare_digest(credentials.credentials, expected_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )
        return True

    def _check_rate_limit(self, request: Request) -> None:
        """Check rate limiting."""
        client_ip = request.client.host if request.client else "unknown"
        rate_config = self.config.get("security", {})
        max_requests = rate_config.get("rate_limit_requests", 100)
        window_seconds = rate_config.get("rate_limit_window_seconds", 60)
        
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=window_seconds)
        
        if client_ip not in self._rate_limits:
            self._rate_limits[client_ip] = {"requests": [], "blocked_until": None}
        
        client_data = self._rate_limits[client_ip]
        if client_data["blocked_until"] and now < client_data["blocked_until"]:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        
        client_data["requests"] = [t for t in client_data["requests"] if t > window_start]
        if len(client_data["requests"]) >= max_requests:
            client_data["blocked_until"] = now + timedelta(seconds=window_seconds)
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        
        client_data["requests"].append(now)

    def _setup_routes(self):
        """Setup all API routes."""

        @self.app.on_event("startup")
        async def startup():
            logger.info("=== MCP Token Auditor Starting ===")
            self.orchestrator = Orchestrator(self.config)
            if not await self.orchestrator.bootstrap():
                logger.error("Orchestrator bootstrap failed")
                return
            
            self.proxy_agent = ProxyInterceptAgent(self.config)
            self.token_audit_agent = TokenAuditAgent(
                token_counter=self.orchestrator.token_counter,
                db=self.orchestrator.db,
                context_window_limit=self.config.get("auditor", {}).get("context_window_limit", 128000),
            )
            self.compression_advisor = CompressionAdvisorAgent(
                token_counter=self.orchestrator.token_counter,
                db=self.orchestrator.db,
                min_confidence=self.config.get("compression_advisor", {}).get("min_confidence", 0.65),
            )
            self.alert_monitor = AlertMonitorAgent(
                db=self.orchestrator.db,
                alerts_config=self.config.get("alerts", {}),
            )
            self.dashboard_broadcast = DashboardBroadcastAgent(self.config)
            logger.info("✓ All agents initialized")

        @self.app.on_event("shutdown")
        async def shutdown():
            if self.orchestrator:
                await self.orchestrator.shutdown()

        @self.app.post("/api/v1/audit/event")
        async def post_audit_event(
            request: Request,
            authenticated: bool = Depends(self._verify_api_key)
        ) -> JSONResponse:
            """Async background processing of audit events to ensure <5ms proxy latency."""
            self._check_rate_limit(request)
            try:
                payload = await request.json()
                
                # Logic for background audit processing
                async def run_audit_background(audit_payload: Dict[str, Any]):
                    try:
                        if not self.token_audit_agent:
                            return

                        # 1. Token Audit Agent (Tiktoken + SQL)
                        event = await self.token_audit_agent.process_audit_payload(audit_payload)
                        if not event:
                            return

                        # 2. Broadcast to dashboard
                        if self.dashboard_broadcast:
                            await self.dashboard_broadcast.broadcast_audit_event(event.to_dict())

                        # 3. Alert Monitor Agent
                        if self.alert_monitor:
                            alerts = await self.alert_monitor.evaluate_audit_event(event)
                            for alert in alerts:
                                if not alert.suppressed and self.dashboard_broadcast:
                                    await self.dashboard_broadcast.broadcast_alert(alert.to_dict())

                        # 4. Compression Advisor Agent
                        if self.compression_advisor and event.tool_name:
                            suggestions = await self.compression_advisor.analyze_tool(
                                server_id=event.server_id,
                                tool_name=event.tool_name,
                                description=event.raw_metadata.get("description", ""),
                                input_schema=event.raw_metadata.get("input_schema", {}),
                            )
                            if suggestions and self.dashboard_broadcast:
                                for suggestion in suggestions:
                                    await self.dashboard_broadcast.broadcast_compression_suggestion(suggestion.to_dict())
                    except Exception as exc:
                        logger.error(f"Background audit failed: {exc}")

                # Dispatch and track task
                task = asyncio.create_task(run_audit_background(payload))
                self.app.state.background_tasks.add(task)
                task.add_done_callback(self.app.state.background_tasks.discard)

                return JSONResponse({"success": True, "audit_id": payload.get("audit_id")})
            except Exception as e:
                logger.error(f"Failed to ingest audit event: {e}")
                return JSONResponse({"error": "Ingestion failed"}, status_code=500)

        @self.app.get("/api/v1/session/summary")
        async def get_session_summary(
            request: Request,
            authenticated: bool = Depends(self._verify_api_key)
        ) -> JSONResponse:
            self._check_rate_limit(request)
            summary = {}
            if self.token_audit_agent:
                summary["token_audit"] = self.token_audit_agent.get_session_summary()
            if self.dashboard_broadcast:
                broadcast_summary = await self.dashboard_broadcast.get_session_summary_rest()
                summary.update(broadcast_summary)
            return JSONResponse(summary)

        @self.app.websocket("/ws/dashboard")
        async def websocket_dashboard(websocket: WebSocket):
            client_id = None
            try:
                await websocket.accept()
                import uuid
                client_id = str(uuid.uuid4())
                if self.dashboard_broadcast:
                    initial_state = await self.dashboard_broadcast.register_client(client_id)
                    await websocket.send_json(initial_state)
                while True:
                    data = await websocket.receive_text()
                    if data == "ping":
                        await websocket.send_text("pong")
            except WebSocketDisconnect:
                if client_id and self.dashboard_broadcast:
                    await self.dashboard_broadcast.unregister_client(client_id)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                if client_id and self.dashboard_broadcast:
                    await self.dashboard_broadcast.unregister_client(client_id)

        @self.app.get("/health")
        async def health_check() -> JSONResponse:
            return JSONResponse({
                "status": "healthy" if self.orchestrator and self.orchestrator.running else "starting",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "version": "1.0.0",
            })

        @self.app.get("/api/v1/metrics")
        async def get_metrics(
            request: Request,
            authenticated: bool = Depends(self._verify_api_key)
        ) -> JSONResponse:
            self._check_rate_limit(request)
            metrics = {}
            if self.orchestrator:
                metrics["orchestrator"] = self.orchestrator.get_metrics()
            import psutil
            process = psutil.Process()
            metrics["system"] = {
                "cpu_percent": process.cpu_percent(),
                "memory_mb": process.memory_info().rss / 1024 / 1024,
                "threads": process.num_threads(),
            }
            return JSONResponse(metrics)

        @self.app.get("/")
        async def root() -> JSONResponse:
            return JSONResponse({
                "name": "MCP Token Auditor",
                "version": "1.0.0",
                "status": "running",
                "environment": "production" if not self._is_development() else "development",
            })

    def run(self, host: str = "127.0.0.1", port: int = 8765):
        logger.info(f"Starting server on {host}:{port}")
        uvicorn.run(self.app, host=host, port=port, log_level="info")

if __name__ == "__main__":
    app_instance = MCPTokenAuditorApp()
    app_instance.run()
