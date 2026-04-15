"""Integration tests for end-to-end workflows."""

import pytest
import asyncio
from src.agents.orchestrator import Orchestrator
from src.agents.proxy_intercept import ProxyInterceptAgent
from src.agents.token_audit import TokenAuditAgent
from src.utils.encodings import TokenCounter


@pytest.mark.asyncio
async def test_end_to_end_audit_flow(sample_audit_payload):
    """Test complete audit flow from intercept to token count."""
    
    # Initialize components
    token_counter = TokenCounter()
    
    proxy_agent = ProxyInterceptAgent({
        "proxy": {
            "upstream_servers": [
                {"id": "test-server", "url": "http://localhost", "transport": "sse"}
            ]
        }
    })
    
    token_audit = TokenAuditAgent(
        token_counter=token_counter,
        db=None,  # Would use temp_db fixture in full integration test
        context_window_limit=128000,
    )
    
    # Process through token audit agent
    event = await token_audit.process_audit_payload(sample_audit_payload)
    
    assert event is not None
    assert event.audit_id == sample_audit_payload["audit_id"]
    assert event.token_breakdown is not None
    assert event.token_breakdown.total_tool_tokens > 0
    assert event.session_cumulative_tokens > 0


@pytest.mark.asyncio
async def test_proxy_intercept_latency_check():
    """Test proxy latency monitoring."""
    from datetime import datetime, timedelta
    
    proxy_agent = ProxyInterceptAgent({
        "proxy": {"upstream_servers": []}
    })
    
    # Within budget (5ms)
    ingress = datetime.utcnow()
    egress = ingress + timedelta(milliseconds=4)
    result = proxy_agent.check_latency(ingress, egress)
    assert result is True
    
    # Exceeds budget
    egress = ingress + timedelta(milliseconds=6)
    result = proxy_agent.check_latency(ingress, egress)
    assert result is False
    assert proxy_agent.latency_warnings > 0
