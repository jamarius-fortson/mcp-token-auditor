"""Input validation and schema checking with Pydantic models."""

import json
import logging
from typing import Any, Dict, Optional, List
from pydantic import BaseModel, Field, validator, model_validator
import yaml

logger = logging.getLogger(__name__)


class SecurityConfig(BaseModel):
    """Security configuration validation."""
    api_key: str = Field(..., min_length=32, description="API key for authentication")
    rate_limit_requests: int = Field(100, gt=0, description="Max requests per window")
    rate_limit_window_seconds: int = Field(60, gt=0, description="Rate limit window in seconds")


class AuditorConfig(BaseModel):
    """Auditor configuration validation."""
    encoding: str = Field("o200k_base", description="Tiktoken encoding name")
    context_window_limit: int = Field(128000, gt=0, description="Context window size in tokens")
    storage_backend: str = Field("sqlite", pattern="^(sqlite|postgresql)$", description="Storage backend")
    storage_path: str = Field("./audit.db", description="Storage path")


class ServerConfig(BaseModel):
    """Server configuration validation."""
    id: str = Field(..., description="Server identifier")
    url: str = Field(..., description="Server URL")
    transport: str = Field("websocket", pattern="^(websocket|sse|stdio)$", description="Transport type")


class ProxyConfig(BaseModel):
    """Proxy configuration validation."""
    listen_port: int = Field(8765, gt=1024, lt=65536, description="Proxy listen port")
    upstream_servers: List[ServerConfig] = Field(default_factory=list, description="Upstream MCP servers")


class AlertRuleConfig(BaseModel):
    """Alert rule configuration validation."""
    threshold: float = Field(..., gt=0, description="Alert threshold value")
    enabled: bool = Field(True, description="Whether rule is enabled")


class AlertsConfig(BaseModel):
    """Alerts configuration validation."""
    rules: Dict[str, AlertRuleConfig] = Field(..., description="Alert rules")
    webhook_url: str = Field("", description="Webhook URL for alerts")


class DashboardConfig(BaseModel):
    """Dashboard configuration validation."""
    websocket_port: int = Field(8766, gt=1024, lt=65536, description="WebSocket port")
    cors_origins: List[str] = Field(default_factory=list, description="Allowed CORS origins")


class CompressionAdvisorConfig(BaseModel):
    """Compression advisor configuration validation."""
    min_confidence: float = Field(0.65, ge=0.0, le=1.0, description="Minimum confidence threshold")
    min_description_tokens: int = Field(8, ge=0, description="Minimum description tokens")
    enabled: bool = Field(True, description="Whether compression advisor is enabled")


class MCPTokenAuditorConfig(BaseModel):
    """Complete configuration validation."""
    auditor: AuditorConfig
    proxy: ProxyConfig
    alerts: AlertsConfig
    dashboard: DashboardConfig
    compression_advisor: CompressionAdvisorConfig
    security: SecurityConfig

    @validator('dashboard')
    def validate_cors_origins(cls, v):
        """Validate CORS origins are proper URLs."""
        for origin in v.cors_origins:
            if not (origin.startswith('http://') or origin.startswith('https://')):
                raise ValueError(f"Invalid CORS origin: {origin}")
        return v

    @model_validator(mode='after')
    def validate_ports_unique(self):
        """Ensure proxy and dashboard ports are different."""
        if self.proxy.listen_port == self.dashboard.websocket_port:
            raise ValueError("Proxy and dashboard ports must be different")
        return self


def validate_config(config_dict: Dict[str, Any]) -> MCPTokenAuditorConfig:
    """Validate complete configuration with Pydantic.
    
    Args:
        config_dict: Configuration dictionary
        
    Returns:
        Validated configuration object
        
    Raises:
        ValidationError: If configuration is invalid
    """
    try:
        config = MCPTokenAuditorConfig(**config_dict)
        logger.info("Configuration validation successful")
        return config
    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        raise


def load_and_validate_config(config_path: str) -> MCPTokenAuditorConfig:
    """Load and validate configuration from YAML file.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Validated configuration object
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        ValidationError: If configuration is invalid
    """
    try:
        with open(config_path, "r") as f:
            config_dict = yaml.safe_load(f)
        
        if not isinstance(config_dict, dict):
            raise ValueError("Configuration must be a dictionary")
        
        return validate_config(config_dict)
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {config_path}")
        raise
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise


def validate_json_rpc(payload: Dict[str, Any]) -> bool:
    """Validate JSON-RPC 2.0 structure.
    
    Args:
        payload: Potential JSON-RPC message
        
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(payload, dict):
        return False
    
    # Required: jsonrpc and either method (request) or result/error (response)
    if payload.get("jsonrpc") != "2.0":
        return False
    
    # Request
    if "method" in payload:
        if not isinstance(payload.get("method"), str):
            return False
        return True
    
    # Response or error
    if "result" in payload or "error" in payload:
        return True
    
    return False


def extract_tool_metadata(tools_response: Dict[str, Any]) -> list:
    """Extract tool metadata from tools/list response.
    
    Args:
        tools_response: Response from tools/list RPC call
        
    Returns:
        List of tool metadata dicts with name, description, input_schema
    """
    tools = []
    
    if not isinstance(tools_response, dict):
        return tools
    
    # Look for tools array in result
    tools_list = tools_response.get("result", {}).get("tools", [])
    if not isinstance(tools_list, list):
        return tools
    
    for tool in tools_list:
        if not isinstance(tool, dict):
            continue
        
        metadata = {
            "name": tool.get("name", ""),
            "description": tool.get("description", ""),
            "input_schema": tool.get("inputSchema", {}),
        }
        
        # Only include if has name
        if metadata["name"]:
            tools.append(metadata)
    
    return tools


def validate_server_id(server_id: str, registered_servers: Dict[str, Any]) -> bool:
    """Validate that server_id is registered.
    
    Args:
        server_id: Server identifier
        registered_servers: Dict of registered server IDs
        
    Returns:
        True if registered, False otherwise
    """
    if not server_id:
        return False
    return server_id in registered_servers


def is_malformed_json_rpc(payload: Any) -> bool:
    """Check if payload is malformed JSON-RPC.
    
    Args:
        payload: Potential JSON-RPC payload
        
    Returns:
        True if malformed, False if valid or non-JSON-RPC
    """
    if not isinstance(payload, dict):
        return True
    
    # Must have jsonrpc field
    if payload.get("jsonrpc") != "2.0":
        return False  # Not JSON-RPC at all, not malformed
    
    # Must have either method or (result/error)
    has_method = "method" in payload
    has_response = "result" in payload or "error" in payload
    
    if not (has_method or has_response):
        return True  # Malformed JSON-RPC
    
    return False
