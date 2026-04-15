# Development & Deployment Guide

## Development Setup

### Local Development

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run development server with auto-reload:**
   ```bash
   make dev
   # or manually:
   python -m uvicorn src.main:MCPTokenAuditorApp.app --reload --host 127.0.0.1 --port 8765
   ```

3. **Run tests:**
   ```bash
   make test
   make test-cov  # with coverage report
   ```

4. **Type checking:**
   ```bash
   mypy src/
   ```

### Project Structure

```
src/
├── main.py                      # FastAPI app entry point
├── agents/
│   ├── orchestrator.py          # Session lifecycle and agent dispatch
│   ├── proxy_intercept.py       # MCP traffic interception
│   ├── token_audit.py           # Token counting engine
│   ├── compression_advisor.py   # Optimization analysis
│   ├── alert_monitor.py         # Alert rules engine
│   └── dashboard_broadcast.py   # WebSocket broadcaster
├── models/
│   └── audit.py                 # Data models (event, alert, etc.)
├── storage/
│   └── database.py              # SQLite persistence layer
└── utils/
    ├── encodings.py             # tiktoken wrapper
    └── validation.py            # Input validation
```

---

## Configuration

### config.yaml

The main configuration file controls:

- **Token Encoding** — Which tiktoken encoding to use (o200k_base for Claude 3.5+)
- **Context Window** — Model's token limit
- **Upstream Servers** — Which MCP servers to proxy and monitor
- **Alert Rules** — Thresholds and alert configuration
- **Dashboard** — WebSocket and CORS settings

**Example:**
```yaml
auditor:
  encoding: "o200k_base"          # ← Token encoding
  context_window_limit: 128000    # ← Model's context limit
  storage_backend: "sqlite"
  storage_path: "./audit.db"

proxy:
  listen_port: 8765
  upstream_servers:
    - id: "filesystem-server"
      url: "http://localhost:3001"
      transport: "sse"            # ← sse | websocket | stdio

alerts:
  rules:
    CTX_WARN:
      threshold: 40               # ← Alert when > 40% context used
      enabled: true
    TOOL_BLOAT:
      threshold: 300              # ← Alert when description > 300 tokens
      enabled: true
  webhook_url: ""                 # ← Optional external webhook
```

---

## Testing

### Unit Tests

```bash
# Run all tests
pytest

# Run specific file
pytest tests/test_encodings.py -v

# Run with coverage
pytest --cov=src tests/
```

### Integration Tests

```bash
pytest tests/test_integration.py -v
```

### Test Coverage Targets

- **Encodings:** Token counting determinism
- **Storage:** Database writes, retrieval, append-only enforcement
- **Agents:** Individual agent logic in isolation
- **Integration:** End-to-end flows (intercept → count → alert → broadcast)
- **API:** HTTP and WebSocket endpoints

---

## Example Usage

### Via REST API

```bash
# Check health
curl http://127.0.0.1:8765/health

# Send audit event
curl -X POST http://127.0.0.1:8765/api/v1/audit/event \
  -H "Content-Type: application/json" \
  -d '{
    "audit_id": "123e4567-e89b-12d3-a456-426614174000",
    "server_id": "filesystem-server",
    "message_type": "tools/list",
    "raw_metadata": {
      "name": "list_files",
      "description": "List files in directory",
      "input_schema": {"type": "object"}
    }
  }'

# Get session summary
curl http://127.0.0.1:8765/api/v1/session/summary
```

### Via Python Script

```bash
python example_client.py
```

### Via WebSocket

```bash
python example_websocket.py
```

---

## Deployment

### Docker

**Build image:**
```bash
docker build -t mcp-token-auditor:latest .
```

**Run container:**
```bash
docker run -p 8765:8765 -p 8766:8766 \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/data:/app/data \
  mcp-token-auditor:latest
```

### Docker Compose (Development)

```bash
docker-compose up
```

This starts:
- **Auditor** on ports 8765 (REST) and 8766 (WebSocket)
- Persistent SQLite database in `./data/audit.db`
- Configuration from `./config/config.yaml`

### Production Considerations

1. **Environment Variables**
   - `CONFIG_PATH` — Path to config.yaml
   - `AUDIT_DB_PATH` — Path to SQLite database
   - `LOG_LEVEL` — Logging level (DEBUG, INFO, WARNING, ERROR)

2. **Database**
   - Use PostgreSQL instead of SQLite for production (modify `src/storage/database.py`)
   - Enable WAL (Write-Ahead Logging) mode for SQLite if using it
   - Regular backups of audit.db

3. **Security**
   - Use HTTPS/WSS in production
   - Implement Bearer token authentication on WebSocket
   - Restrict CORS origins to known domains
   - Run in a dedicated security group/network

4. **Monitoring**
   - Log all audit events to central logging system
   - Monitor latency breaches
   - Alert on SYSTEM_FAULT events
   - Track database growth

5. **Scalability**
   - Stateless HTTP/WebSocket servers (scale horizontally)
   - Shared PostgreSQL database for multi-instance deployments
   - Redis for distributed alert state if needed

---

## Troubleshooting

### Auditor won't start

```
Error: Configuration validation failed
```
→ Check `config/config.yaml` is valid YAML and has required fields.

### Token counts seem wrong

```
Token count: 0
```
→ Verify tiktoken encoding in config matches model (o200k_base for Claude 3.5+).

### Alerts not firing

```
No alerts in dashboard
```
→ Check alert rules are `enabled: true` in config.yaml
→ Verify thresholds are reasonable for your use case

### WebSocket connection fails

```
WebSocket connection failed
```
→ Check CORS origins in config.yaml
→ Verify port 8766 is not blocked by firewall
→ Ensure client is connecting to correct URL (ws://, not http://)

---

## Performance Tips

1. **Latency**
   - Proxy intercept adds < 5ms p99 overhead
   - Token counting is synchronous; consider async batching for high-volume scenarios
   - Dashboard broadcasts are async (non-blocking)

2. **Database**
   - Indices are created on `server_id`, `tool_name`, `timestamp`
   - Consider table partitioning by date for long-running sessions
   - Use `audit_id` for rapid event correlation

3. **Memory**
   - Event buffer limited to 1000 entries (configurable)
   - Alert buffer limited to 500 entries
   - Use Pydantic models for memory-efficient serialization

---

## Future Extensions

- [ ] PostgreSQL backend for production deployments
- [ ] Multi-session management and correlation
- [ ] Machine learning baselines for anomaly detection
- [ ] Webhook integrations for Slack/PagerDuty alerts
- [ ] React dashboard frontend reference implementation
- [ ] Distributed tracing (OpenTelemetry integration)
- [ ] Compression suggestion auto-application API

---

**Last Updated:** March 25, 2025
