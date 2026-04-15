# MCP Token Auditor — Quick Reference

## 🚀 Start Server
```bash
python -m src.main
# or with auto-reload (dev):
uvicorn src.main:MCPTokenAuditorApp.app --reload --host 127.0.0.1 --port 8765
```

## 📊 API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Health check |
| GET | `/` | Root info |
| GET | `/api/v1/session/summary` | Session cumulative stats |
| POST | `/api/v1/audit/event` | Send audit payload |
| WS | `/ws/dashboard` | Real-time WebSocket stream |

## 🔌 WebSocket Events

```json
{
  "event_type": "TOKEN_AUDIT_EVENT | ALERT_FIRED | COMPRESSION_SUGGESTION | SESSION_SUMMARY | SYSTEM_FAULT | LATENCY_BREACH",
  "timestamp": "ISO8601",
  "data": { /* event-specific data */ }
}
```

## ⚙️ Configuration Quick Edits

**Change token encoding:**
```yaml
auditor:
  encoding: "cl100k_base"  # or "o200k_base" (default)
```

**Add upstream server:**
```yaml
proxy:
  upstream_servers:
    - id: "my-server"
      url: "http://localhost:3000"
      transport: "websocket"
```

**Modify alert threshold:**
```yaml
alerts:
  rules:
    CTX_CRITICAL:
      threshold: 70  # Changed from 60
      enabled: true
```

## 🧪 Test Commands

```bash
pytest                           # All tests
pytest tests/test_encodings.py   # Specific file
pytest -v                        # Verbose
pytest --cov=src                 # With coverage
pytest -k "test_latency"         # By keyword
```

## 🎯 Common Tasks

### Send a Test Audit Event
```bash
curl -X POST http://127.0.0.1:8765/api/v1/audit/event \
  -H "Content-Type: application/json" \
  -d '{
    "audit_id": "test-123",
    "server_id": "filesystem-server",
    "message_type": "tools/list",
    "raw_metadata": {
      "name": "list_files",
      "description": "List files in directory",
      "input_schema": {"type": "object"}
    },
    "timestamp_ingress": "2025-03-25T14:32:01.482310Z",
    "timestamp_egress": "2025-03-25T14:32:01.485310Z"
  }'
```

### Get Session Summary
```bash
curl http://127.0.0.1:8765/api/v1/session/summary | python -m json.tool
```

### Check Auditor Health
```bash
curl http://127.0.0.1:8765/health
```

### Watch Test Output
```bash
pytest tests/test_encodings.py -v -s --tb=short
```

## 🐳 Docker

```bash
# Build
docker build -t auditor:latest .

# Run
docker run -p 8765:8765 -p 8766:8766 auditor:latest

# With compose
docker-compose up

# Build and stop old containers
docker-compose up --build
```

## 📈 Monitor Logs

```bash
# Real-time logs (with docker-compose)
docker-compose logs -f auditor

# Python console logging
export LOG_LEVEL=DEBUG
python -m src.main
```

## 🧠 Core Functions

### Token Counting
```python
from src.utils.encodings import TokenCounter

counter = TokenCounter(encoding_name="o200k_base")
tokens = counter.count("Hello world")
# or for tool metadata:
counts = counter.count_tool_metadata(
    name="list_files",
    description="...",
    schema={...}
)
# Returns: {"name_tokens": N, "description_tokens": M, "schema_tokens": K, "total_tool_tokens": X}
```

### Audit Event Processing
```python
from src.agents.token_audit import TokenAuditAgent

auditor = TokenAuditAgent(token_counter, db, context_window_limit=128000)
event = await auditor.process_audit_payload(payload)
summary = auditor.get_session_summary()
```

### Alert Evaluation
```python
from src.agents.alert_monitor import AlertMonitorAgent

monitor = AlertMonitorAgent(db, alerts_config)
alerts = await monitor.evaluate_audit_event(audit_event)
```

### WebSocket Broadcast
```python
from src.agents.dashboard_broadcast import DashboardBroadcastAgent

broadcaster = DashboardBroadcastAgent(config)
await broadcaster.broadcast_audit_event(event_dict)
await broadcaster.broadcast_alert(alert_dict)
```

## 🔍 Debugging

### View SQLite Database
```bash
sqlite3 audit.db

# Common queries:
.tables
SELECT COUNT(*) FROM audit_events;
SELECT * FROM audit_events LIMIT 5;
SELECT * FROM alerts WHERE rule_id = 'CTX_CRITICAL';
```

### Check Port Usage
```bash
# Unix/Linux/Mac
lsof -i :8765
lsof -i :8766

# Windows
netstat -ano | findstr :8765
```

### Enable Debug Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📦 File Structure by Agent

| Agent | File | Key Classes |
|-------|------|-------------|
| 1. Orchestrator | `src/agents/orchestrator.py` | `Orchestrator` |
| 2. Proxy Intercept | `src/agents/proxy_intercept.py` | `ProxyInterceptAgent` |
| 3. Token Audit | `src/agents/token_audit.py` | `TokenAuditAgent` |
| 4. Compression Advisor | `src/agents/compression_advisor.py` | `CompressionAdvisorAgent` |
| 5. Alert Monitor | `src/agents/alert_monitor.py` | `AlertMonitorAgent` |
| 6. Dashboard Broadcast | `src/agents/dashboard_broadcast.py` | `DashboardBroadcastAgent` |

## 🛠️ Setup Checklist

- [ ] Python 3.9+ installed
- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] `config/config.yaml` edited with your servers
- [ ] Upstream MCP servers available
- [ ] Ports 8765 (API) and 8766 (WebSocket) available
- [ ] Run `python -m src.main`
- [ ] Test with `python example_client.py`
- [ ] Connect WebSocket with `python example_websocket.py`

## 🎓 Understanding the Flow

```
1. Client → POST /api/v1/audit/event
2. Orchestrator routes → TokenAuditAgent
3. TokenAuditAgent:
   - Counts tokens with tiktoken
   - Updates session cumulative
   - Persists to SQLite
   - Emits enriched event
4. Alert Monitor evaluates rules
5. Compression Advisor suggests optimizations
6. Dashboard Broadcast sends WebSocket updates
7. React Dashboard displays in real-time
```

## 🚨 Error Codes

| Code | Meaning | Fix |
|------|---------|-----|
| `CONFIG_INVALID` | Bad config.yaml | Check YAML syntax |
| `PROXY_LATENCY_BREACH` | > 5ms latency | Normal warning, check system load |
| `AUDIT_WRITE_FAILURE` | Database write failed | Check disk space and permissions |
| `UNKNOWN_SERVER_ID` | Server not registered | Add to config.yaml |
| `ENCODING_MISMATCH` | Token encoding changed mid-session | Restart with consistent encoding |
| `SYSTEM_FAULT` | Critical unrecoverable error | Check logs, restart |

## 💡 Performance Tips

- Token counting is O(1) with tiktoken
- Database queries use indices on `server_id`, `tool_name`, `timestamp`
- Event buffer limited to 1000 (configurable)
- WebSocket broadcasts are async (non-blocking)
- Proxy latency budget: 5ms p99

## 🔐 Security Checklist

- [ ] No LLM conversation content stored (only token counts)
- [ ] Audit trail append-only (never modified)
- [ ] Sensitive data not logged
- [ ] CORS origins restricted in config
- [ ] WebSocket should implement bearer token auth (production)
- [ ] Database backups configured
- [ ] HTTPS/WSS in production

---

**Need help?** See [GETTING_STARTED.md](GETTING_STARTED.md) or [README.md](README.md)
