"""Example: Real-time WebSocket client for dashboard."""

import asyncio
import json
import websockets
from datetime import datetime


async def dashboard_client():
    """Connect to dashboard WebSocket and listen for events."""
    
    uri = "ws://127.0.0.1:8766/ws/dashboard"
    
    print("🔗 Connecting to dashboard WebSocket...")
    async with websockets.connect(uri) as websocket:
        print("✓ Connected to dashboard")
        
        # Receive initial state
        initial_state = await websocket.recv()
        state_msg = json.loads(initial_state)
        print(f"\n📊 Initial State:")
        print(f"  Event Type: {state_msg.get('event_type')}")
        print(f"  Timestamp: {state_msg.get('timestamp')}")
        print(f"  Connected Clients: {state_msg.get('state', {}).get('connected_clients', 'N/A')}")
        
        # Send heartbeat
        print("\n💓 Sending heartbeat...")
        await websocket.send("ping")
        pong = await websocket.recv()
        print(f"Received: {pong}")
        
        # Listen for events
        print("\n👂 Listening for events (press Ctrl+C to stop)...\n")
        try:
            while True:
                event = await websocket.recv()
                msg = json.loads(event)
                
                event_type = msg.get("event_type", "UNKNOWN")
                timestamp = msg.get("timestamp", "N/A")
                
                if event_type == "TOKEN_AUDIT_EVENT":
                    data = msg.get("data", {})
                    print(f"📊 TOKEN_AUDIT_EVENT ({timestamp})")
                    print(f"   Tool: {data.get('tool_name')}")
                    print(f"   Tokens: {data.get('token_breakdown', {}).get('total_tool_tokens')}")
                    print(f"   Context Usage: {data.get('context_window_pct')}%")
                    print()
                
                elif event_type == "ALERT_FIRED":
                    data = msg.get("data", {})
                    severity = data.get("severity", "UNKNOWN")
                    rule_id = data.get("rule_id", "UNKNOWN")
                    print(f"🚨 ALERT_FIRED ({timestamp})")
                    print(f"   Rule: {rule_id} [{severity}]")
                    print(f"   Message: {data.get('message')}")
                    print(f"   Current Value: {data.get('current_value')}")
                    print(f"   Threshold: {data.get('threshold_value')}")
                    print()
                
                elif event_type == "COMPRESSION_SUGGESTION":
                    data = msg.get("data", {})
                    print(f"💡 COMPRESSION_SUGGESTION ({timestamp})")
                    print(f"   Tool: {data.get('tool_name')}")
                    print(f"   Savings: {data.get('total_projected_savings')} tokens")
                    print()
                
                elif event_type == "SESSION_SUMMARY":
                    data = msg.get("data", {})
                    print(f"📈 SESSION_SUMMARY ({timestamp})")
                    print(f"   Cumulative Tokens: {data.get('session_cumulative_tokens')}")
                    print()
                
                else:
                    print(f"📡 {event_type} ({timestamp})")
                
        except KeyboardInterrupt:
            print("\n✓ Disconnected")


if __name__ == "__main__":
    asyncio.run(dashboard_client())
