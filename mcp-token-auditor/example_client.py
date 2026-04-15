"""Example: Send audit events to the Token Auditor via REST API."""

import requests
import json
from datetime import datetime
import uuid

# Configuration
AUDITOR_BASE_URL = "http://127.0.0.1:8765"
AUDITOR_HEALTH_URL = f"{AUDITOR_BASE_URL}/health"
AUDITOR_AUDIT_URL = f"{AUDITOR_BASE_URL}/api/v1/audit/event"
AUDITOR_SUMMARY_URL = f"{AUDITOR_BASE_URL}/api/v1/session/summary"


def check_auditor_health():
    """Check if auditor is running."""
    try:
        response = requests.get(AUDITOR_HEALTH_URL, timeout=2)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


def send_audit_event(
    server_id: str,
    tool_name: str,
    description: str,
    input_schema: dict,
    transport: str = "sse",
) -> dict:
    """Send an audit event to the auditor.
    
    Args:
        server_id: MCP server identifier
        tool_name: Tool name
        description: Tool description
        input_schema: JSON schema for tool inputs
        transport: Transport type (sse, websocket, stdio)
        
    Returns:
        Response from auditor
    """
    
    # Generate unique audit ID
    audit_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    
    # Create audit payload
    payload = {
        "audit_id": audit_id,
        "timestamp_ingress": now,
        "timestamp_egress": now,
        "server_id": server_id,
        "transport": transport,
        "message_type": "tools/list",
        "raw_metadata": {
            "name": tool_name,
            "description": description,
            "input_schema": input_schema,
        }
    }
    
    try:
        response = requests.post(
            AUDITOR_AUDIT_URL,
            json=payload,
            timeout=5,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error sending audit event: {e}")
        return {"error": str(e)}


def get_session_summary() -> dict:
    """Get current session summary from auditor."""
    try:
        response = requests.get(AUDITOR_SUMMARY_URL, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error getting session summary: {e}")
        return {"error": str(e)}


def main():
    """Example usage."""
    
    # Step 1: Check auditor health
    print("🔍 Checking auditor health...")
    if not check_auditor_health():
        print("❌ Auditor is not running. Start it with: python -m src.main")
        return
    print("✓ Auditor is running")
    
    # Step 2: Send some example audit events
    print("\n📊 Sending audit events...")
    
    tools = [
        {
            "server_id": "filesystem-server",
            "tool_name": "list_files",
            "description": "Recursively list all files in a directory. Returns a list of file paths.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to list"},
                    "recursive": {"type": "boolean", "description": "Whether to recurse into subdirectories"},
                },
                "required": ["path"]
            }
        },
        {
            "server_id": "github-server",
            "tool_name": "search_repositories",
            "description": "Search GitHub repositories by keyword. Returns matching repositories with metadata.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query string"},
                    "language": {"type": "string", "description": "Programming language filter"},
                    "sort": {"type": "string", "enum": ["stars", "forks", "updated"], "description": "Sort order"},
                },
                "required": ["query"]
            }
        },
        {
            "server_id": "github-server",
            "tool_name": "get_repository_info",
            "description": "Get detailed information about a GitHub repository including stars, forks, contributors.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "name": {"type": "string"},
                },
                "required": ["owner", "name"]
            }
        },
    ]
    
    for tool in tools:
        result = send_audit_event(**tool)
        print(f"  ✓ {tool['tool_name']}: {result}")
    
    # Step 3: Get session summary
    print("\n📈 Session Summary")
    summary = get_session_summary()
    
    if "token_audit" in summary:
        token_info = summary["token_audit"]
        print(f"  Session Cumulative Tokens: {token_info['session_cumulative_tokens']}")
        print(f"  Context Window Usage: {token_info['context_window_pct']}%")
        print(f"  Per-Server Breakdown:")
        for server_id, tokens in token_info.get("server_tokens", {}).items():
            print(f"    - {server_id}: {tokens} tokens")
    
    print("\n✅ Example completed successfully!")
    print("\n💡 Tip: Connect to the WebSocket at ws://localhost:8766/ws/dashboard")
    print("        to see real-time alerts and compression suggestions.")


if __name__ == "__main__":
    main()
