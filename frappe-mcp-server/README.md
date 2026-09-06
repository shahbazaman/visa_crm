# Frappe CRM MCP Server (Phase 3: Dual Stdio & Remote SSE)

A secure, standalone **Model Context Protocol (MCP)** server enabling **Google Gemini** (Antigravity IDE, Gemini CLI, and GenAI SDK agents) to query the production Frappe CRM through the controlled Phase 1 read-only API (`visa_crm.api.mcp.get_today_leads`).

---

## 1. Architecture

```
???????????????????????????          HTTPS (SSE)          ?????????????????????????????         HTTPS (RPC)        ???????????????????????????
? Google Gemini Client    ? ????????????????????????????> ? Remote MCP Server         ? ?????????????????????????> ? Frappe Cloud (Prod)     ?
? (Gemini CLI /           ? <???????????????????????????? ? (frappe-mcp-server)       ? <????????????????????????? ? middleeast.frappe.cloud ?
?  Antigravity Remote /   ?    Auth: Bearer <MCP_TOKEN>   ?                           ?   Auth: token <KEY>:<SEC> ?                         ?
?  GenAI SDK Agent)       ?    Endpoint: /sse             ?   - Validates MCP_TOKEN   ?   Endpoint:               ?                         ?
???????????????????????????    Endpoint: /messages        ?   - Route: GET /health    ?   /api/method/            ?                         ?
                                                          ?   - Single tool:          ?   visa_crm.api.mcp.       ?                         ?
                                                          ?     get_today_leads       ?   get_today_leads         ?                         ?
                                                          ?????????????????????????????                           ???????????????????????????
                                                                                                                               ?
                                                                                                                     Controlled Phase 1 API
                                                                                                                               ?
                                                                                                                               ?
                                                                                                                        CRM Lead Records
                                                                                                                        (Read-Only Data)
```

- **Dual-Transport**: Supports both **Stdio** (local, zero-network-port for Antigravity) and **SSE** (network/cloud hosting for remote Gemini clients).
- **Two-Tier Security**: Remote clients authenticate to the MCP server via `MCP_AUTH_TOKEN`. The MCP server uses server-side `FRAPPE_API_KEY` and `FRAPPE_API_SECRET` to talk to Frappe Cloud. **Frappe credentials are NEVER exposed to Gemini or sent in responses.**
- **Target Frappe Endpoint**: `https://middleeast.frappe.cloud/api/method/visa_crm.api.mcp.get_today_leads`

---

## 2. Security Guarantees

1. **Zero Dynamic SQL & Fixed DocType**: Only queries `CRM Lead` records created today via the controlled server-side Frappe API.
2. **Read-Only**: Exposes a single, parameterless reporting tool (`get_today_leads`). No write, edit, delete, or SQL execution tools are exposed.
3. **No Credential Exposure**: Frappe credentials remain server-side in `.env`.
4. **Controlled Errors**: All network, timeout, or authentication issues return safe, standardized user messages without internal stack traces.

---

## 3. Configuration (`.env`)

Copy `.env.example` to `.env` and configure:

```bash
# Frappe CRM Production Connection (Server-Side)
FRAPPE_BASE_URL=https://middleeast.frappe.cloud
FRAPPE_API_KEY=your_frappe_api_key_here
FRAPPE_API_SECRET=your_frappe_api_secret_here
HTTP_TIMEOUT=15.0

# Optional: Remote MCP Client Security (for SSE transport)
MCP_AUTH_TOKEN=your_custom_secret_bearer_token_here
MCP_HOST=127.0.0.1
MCP_PORT=8000

# Optional: Google Gemini API Key (for standalone SDK testing)
GEMINI_API_KEY=your_gemini_api_key_here
```

> [!CAUTION]
> Never commit `.env` to Git. The `.gitignore` file is configured to strictly exclude `.env` files.

---

## 4. Running the Server

### A. Local Stdio Transport (Default)
Used by local IDEs (like Google Antigravity) with zero open network ports:
```bash
python server.py --transport stdio
```

### B. Remote SSE Transport
Used for network/cloud access by remote Gemini clients:
```bash
python server.py --transport sse --host 0.0.0.0 --port 8000
```
Or via production ASGI runner:
```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --workers 2
```

Endpoints:
- **`GET /health`**: Public health check (returns `{"status": "ok", "service": "frappe-crm-mcp", "tools": ["get_today_leads"]}`).
- **`GET /sse`**: MCP SSE connection endpoint (requires `Authorization: Bearer <MCP_AUTH_TOKEN>` if configured).
- **`POST /messages/`**: MCP message channel for JSON-RPC requests.

---

## 5. Client Configuration

### 1. Google Antigravity IDE (Local Stdio)
Add to `~/.gemini/config/mcp_config.json`:
```json
{
  "mcpServers": {
    "frappe-crm": {
      "command": "wsl.exe",
      "args": [
        "-d",
        "Ubuntu-22.04",
        "--",
        "/home/shahbaz/frappe-bench/apps/visa_crm/frappe-mcp-server/.venv/bin/python",
        "/home/shahbaz/frappe-bench/apps/visa_crm/frappe-mcp-server/server.py"
      ],
      "env": {
        "FRAPPE_BASE_URL": "https://middleeast.frappe.cloud"
      }
    }
  }
}
```

### 2. Google Antigravity IDE (Remote SSE)
Add to `~/.gemini/config/mcp_config.json`:
```json
{
  "mcpServers": {
    "frappe-crm": {
      "serverUrl": "https://<your-mcp-domain>/sse"
    }
  }
}
```

### 3. Gemini CLI / Remote Agent
In `settings.json`:
```json
{
  "mcpServers": {
    "frappe-crm": {
      "transport": "sse",
      "url": "https://<your-mcp-domain>/sse",
      "headers": {
        "Authorization": "Bearer <YOUR_MCP_AUTH_TOKEN>"
      }
    }
  }
}
```

---

## 6. Verification Tests

```bash
# Run all verification tests
python tests/test_1_server_startup.py
python tests/test_2_https_connectivity.py
python tests/test_3_4_auth_validation.py
python tests/test_5_schema_validation.py
python tests/test_6_mcp_tool_execution.py    # Local Stdio protocol test
python tests/test_remote_mcp.py              # Remote SSE & Health check test
```

---

## 7. Production Hosting Options

### Option A: Systemd Service (Linux VPS / VM)
`/etc/systemd/system/frappe-mcp.service`:
```ini
[Unit]
Description=Frappe CRM Remote MCP Server
After=network.target

[Service]
User=shahbaz
WorkingDirectory=/home/shahbaz/frappe-bench/apps/visa_crm/frappe-mcp-server
ExecStart=/home/shahbaz/frappe-bench/apps/visa_crm/frappe-mcp-server/.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
EnvironmentFile=/home/shahbaz/frappe-bench/apps/visa_crm/frappe-mcp-server/.env

[Install]
WantedBy=multi-user.target
```

### Option B: Reverse Proxy (Caddy with automatic TLS)
```caddy
mcp.yourcompany.com {
    reverse_proxy 127.0.0.1:8000
}
```

### Option C: Cloudflare Tunnel
```bash
cloudflared tunnel --url http://127.0.0.1:8000
```
Provides an encrypted public HTTPS endpoint (`https://<tunnel-id>.trycloudflare.com`) without opening firewall ports.
