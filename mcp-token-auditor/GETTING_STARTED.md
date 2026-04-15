# 🚀 MCP Token Auditor — Getting Started

This is your **production-ready MCP Token Auditor** system with all 6 agents fully implemented.

---

## ✅ What's Included

### Project Structure
```
mcp-token-auditor/
├── src/                                # Main application code
│   ├── agents/
│   │   ├── orchestrator.py            # Master coordinator (Agent 1)
│   │   ├── proxy_intercept.py         # MCP traffic interceptor (Agent 2)
│   │   ├── token_audit.py             # Token counter (Agent 3)
│   │   ├── compression_advisor.py     # Optimization analyzer (Agent 4)
│   │   ├── alert_monitor.py           # Alert engine (Agent 5)
│   │   └── dashboard_broadcast.py     # WebSocket broadcaster (Agent 6)
│   ├── models/
│   │   └── audit.py                   # Data models (AuditEvent, Alert, etc.)
│   ├── storage/
│   │   └── database.py                # SQLite persistence layer
│   ├── utils/
│   │   ├── encodings.py               # tiktoken wrapper for token counting
│   │   └── validation.py              # MCP message validation
│   └── main.py                        # FastAPI application
│
├── config/
│   └── config.yaml                    # Configuration (encoding, servers, alerts, etc.)
│
├── tests/
│   ├── conftest.py                    # Pytest fixtures
│   ├── test_encodings.py              # Token counting tests
│   ├── test_storage.py                # Database persistence tests
│   └── test_integration.py            # End-to-end tests
│
├── example_client.py                  # Example: Send audit events via REST
├── example_websocket.py               # Example: Listen to real-time events via WebSocket
├── Makefile                           # Development commands (make dev, make test, etc.)
├── Dockerfile                         # Container image
├── docker-compose.yml                 # Local development stack
├── README.md                          # Full documentation
├── DEVELOPMENT.md                     # Development and deployment guide
├── GETTING_STARTED.md                 # (this file)
└── requirements.txt                   # Python dependencies
```

---

## 🏃 Quick Start (5 minutes)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Start the Server
```bash
python -m src.main
```

You should see:
```
2025-03-25 14:32:01,234 - src.main - INFO - === MCP Token Auditor Starting ===
2025-03-25 14:32:01,345 - src.agents.orchestrator - INFO - ✓ Database initialized
...
2025-03-25 14:32:01,456 - src.main - INFO - === MCP Token Auditor Ready ===
INFO:     Uvicorn running on http://127.0.0.1:8765
```

### 3. Test It Out

**Terminal 1 — Run the example client:**
```bash
python example_client.py
```

You should see audit events being processed and session summary.

**Terminal 2 — Connect to WebSocket for real-time updates:**
```bash
python example_websocket.py
```

You'll see:
- 📊 TOKEN_AUDIT_EVENT — Token counts for each tool
- 🚨 ALERT_FIRED — When thresholds are exceeded
- 💡 COMPRESSION_SUGGESTION — Optimization opportunities

### 4. View API Documentation
```
http://127.0.0.1:8765/docs
```

---

## 🎯 Core Components

### 1. **Orchestrator Agent** (`src/agents/orchestrator.py`)
- Bootstraps all agents at startup
- Validates configuration
- Routes incoming messages
- Health-checks upstream servers
- Implements safe-passthrough failover

**Key Methods:**
```python
orchestrator = Orchestrator(config)
await orchestrator.bootstrap()
```

### 2. **Proxy Intercept Agent** (`src/agents/proxy_intercept.py`)
- Intercepts MCP traffic bidirectionally
- Extracts tool metadata from `tools/list` responses
- Attaches unique `audit_id` to every message
- Monitors proxy latency (< 5ms p99)
- Passes through malformed JSON-RPC unmodified

**Key Methods:**
```python
proxy = ProxyInterceptAgent(config)
message, audit_event = await proxy.intercept_request(message, "filesystem-server")
```

### 3. **Token Audit Agent** (`src/agents/token_audit.py`)
- Counts tokens for tool name, description, and input_schema
- Uses `tiktoken` for deterministic counting
- Maintains session-cumulative and per-server tracking
- Persists audit records to SQLite
- Calculates context window usage percentage

**Key Methods:**
```python
auditor = TokenAuditAgent(token_counter, db, context_window_limit=128000)
event = await auditor.process_audit_payload(audit_payload)
summary = auditor.get_session_summary()
```

### 4. **Compression Advisor Agent** (`src/agents/compression_advisor.py`)
- Analyzes tool descriptions for optimization opportunities
- Applies 5 heuristics: redundancy, verbosity, schema bloat, Cloudflare code mode, deduplication
- Scores suggestions by confidence (0.0–1.0)
- Only emits suggestions with confidence ≥ 0.65
- Helps reduce token consumption

**Key Methods:**
```python
advisor = CompressionAdvisorAgent(token_counter, min_confidence=0.65)
suggestions = await advisor.analyze_tool(server_id, tool_name, description, schema)
```

### 5. **Alert Monitor Agent** (`src/agents/alert_monitor.py`)
- Evaluates 6 built-in alert rules
- Implements 30-second debouncing (except CRITICAL)
- Persists alerts to database
- Buffers alerts if webhook is down (max 500 entries)

**Built-in Rules:**
- `CTX_WARN` — Tool metadata > 40% context
- `CTX_CRITICAL` — Tool metadata > 60% context (never suppressed)
- `TOOL_BLOAT` — Description > 300 tokens
- `SCHEMA_BLOAT` — Schema > 400 tokens
- `CALL_SPIKE` — > 60 calls per minute
- `SERVER_DRIFT` — Token count deviates > 25% from baseline

**Key Methods:**
```python
monitor = AlertMonitorAgent(db, alerts_config)
alerts = await monitor.evaluate_audit_event(audit_event)
```

### 6. **Dashboard Broadcast Agent** (`src/agents/dashboard_broadcast.py`)
- Maintains real-time WebSocket connections to dashboard clients
- Broadcasts events with selective subscription
- Buffers events for new clients (ring buffer, max 1000)
- Provides REST endpoint for non-WebSocket consumers

**Event Types:**
- `TOKEN_AUDIT_EVENT` — Token count updates
- `ALERT_FIRED` — Alert notifications
- `COMPRESSION_SUGGESTION` — Optimization suggestions
- `SESSION_SUMMARY` — Aggregated metrics
- `SYSTEM_FAULT` — Critical errors
- `LATENCY_BREACH` — Performance warnings

**Key Methods:**
```python
broadcaster = DashboardBroadcastAgent(config)
await broadcaster.broadcast_audit_event(event_dict)
await broadcaster.broadcast_alert(alert_dict)
```

---

## 📊 Data Flow

```
Incoming MCP Traffic
        ↓
┌─────────────────────────────────────┐
│  Proxy Intercept Agent (Agent 2)    │  ← Attach audit_id, timestamp
│  - Extracts tool metadata           │  ← Check latency
│  - Validates JSON-RPC              │
└─────────────────────────────────────┘
        ↓
┌─────────────────────────────────────┐
│  Token Audit Agent (Agent 3)        │  ← Count tokens with tiktoken
│  - Count name, description, schema  │  ← Update session cumulative
│  - Persist to SQLite               │  ← Calculate context %
└─────────────────────────────────────┘
        ↓
   ┌────┴────┬─────────┐
   ↓         ↓         ↓
┌─────────┐ ┌──────────┐ ┌──────────────┐
│ Alert   │ │ Compress │ │ Dashboard    │
│ Monitor │ │ Advisor  │ │ Broadcast    │
│(Agent 5)│ │(Agent 4) │ │ (Agent 6)    │
└────┬────┘ └──────────┘ └──────────────┘
     │
     ↓
  Connected Clients
  - React Dashboard
  - Mobile App
  - Monitoring Tools
```

---

## 🔧 Configuration

Edit `config/config.yaml`:

```yaml
auditor:
  encoding: "o200k_base"              # Token encoding (see tiktoken docs)
  context_window_limit: 128000        # Model's context window
  storage_backend: "sqlite"           # Storage backend
  storage_path: "./audit.db"          # Database path

proxy:
  listen_port: 8765                   # API port
  upstream_servers:
    - id: "filesystem-server"
      url: "http://localhost:3001"
      transport: "sse"                # sse | websocket | stdio

alerts:
  rules:
    CTX_WARN: { threshold: 40, enabled: true }
    CTX_CRITICAL: { threshold: 60, enabled: true }
    TOOL_BLOAT: { threshold: 300, enabled: true }
    SCHEMA_BLOAT: { threshold: 400, enabled: true }
    CALL_SPIKE: { threshold: 60, enabled: true }
    SERVER_DRIFT: { threshold: 25, enabled: true }

dashboard:
  websocket_port: 8766
  cors_origins:
    - "http://localhost:5173"
```

---

## 🧪 Testing

Run all tests:
```bash
pytest -v
```

Run specific test:
```bash
pytest tests/test_encodings.py -v
```

With coverage:
```bash
pytest --cov=src tests/
```

---

## 📝 Development Commands

```bash
make install      # Install dependencies
make dev          # Run server with auto-reload
make test         # Run tests
make test-cov     # Tests with coverage report
make lint         # Type checking
make format       # Auto-format code
make clean        # Remove cache/artifacts
make run          # Run production server
make health       # Check server health
```

---

## 🐳 Docker Deployment

**Build:**
```bash
docker build -t mcp-token-auditor:latest .
```

**Run:**
```bash
docker run -p 8765:8765 -p 8766:8766 \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/data:/app/data \
  mcp-token-auditor:latest
```

**Or with Docker Compose:**
```bash
docker-compose up
```

---

## 📦 Example Usage

### Send Audit Events (REST API)
```bash
python example_client.py
```

### Listen to Real-Time Events (WebSocket)
```bash
python example_websocket.py
```

### Direct API Calls
```bash
# Health check
curl http://127.0.0.1:8765/health

# Send event
curl -X POST http://127.0.0.1:8765/api/v1/audit/event \
  -H "Content-Type: application/json" \
  -d '{"server_id": "test", "tool_name": "list_files", ...}'

# Get summary
curl http://127.0.0.1:8765/api/v1/session/summary
```

---

## 🎓 Key Concepts

### Determinism
All token counts are produced by `tiktoken` directly—zero approximations.

### Append-Only Audit Log
Every audit event written to database is immutable. No modifications after write.

### Traceability
Every action is tied to a UUID `audit_id` for correlation across the system.

### Non-Interference
The system is a read-only observer. It never modifies, delays, or drops MCP messages.

### Encoding Consistency
All tokens in a session use the same tiktoken encoding, locked at session start.

---

## 🚨 Failure Modes & Recovery

| Condition | Recovery |
|---|---|
| Latency > 5ms | Log warning, continue |
| Database write fails | Halt, surface error, retry |
| Encoding mismatch (mid-session) | Reject, enforce session encoding |
| Malformed JSON-RPC | Pass through unmodified, log |
| WebSocket down | Buffer in-memory (max 500), flush on reconnect |
| Unrecoverable error | Emit SYSTEM_FAULT, enter safe-passthrough mode |

---

## 📚 Next Steps

1. **Understand the System Prompt** — Read the [README.md](README.md) for the full specification
2. **Explore the Code** — Start with `src/main.py` and follow the agent flow
3. **Run Examples** — Try `example_client.py` and `example_websocket.py`
4. **Write Tests** — Add tests in `tests/` for custom integrations
5. **Configure** — Edit `config/config.yaml` for your MCP servers and alert thresholds
6. **Deploy** — Use Docker or production WSGI server (gunicorn + reverse proxy)

---

## 🆘 Troubleshooting

**"Auditor won't start"**
→ Check `config/config.yaml` for syntax errors and required fields

**"Token counts are zero"**
→ Verify tiktoken encoding in config (o200k_base for Claude 3.5+)

**"WebSocket connection refused"**
→ Check port 8766 is not blocked, verify CORS origins in config

**"Database locked"**
→ Ensure only one instance is running, or use PostgreSQL in production

---

## 📞 Support

- **System Prompt:** Full specification in [README.md](README.md)
- **Development Guide:** [DEVELOPMENT.md](DEVELOPMENT.md)
- **API Docs:** http://127.0.0.1:8765/docs (after starting server)

---

**Ready to audit! Start the server with:**
```bash
python -m src.main
```

**Questions? Check:**
- [README.md](README.md) — Full specification
- [DEVELOPMENT.md](DEVELOPMENT.md) — Development & deployment
- [config/config.yaml](config/config.yaml) — Configuration details

---

**Version:** 1.0.0  
**Status:** Production-Ready  
**Last Updated:** March 25, 2025
