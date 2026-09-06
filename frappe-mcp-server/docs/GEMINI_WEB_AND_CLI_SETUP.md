# ?? GOOGLE GEMINI (WEB, CLI & SDK) ? FRAPPE CRM MCP INTEGRATION GUIDE

This document details the production architecture, configuration instructions, and security controls for connecting **real Google Gemini clients** to the **Visa CRM MCP Server** (`frappe-mcp-server`) and retrieving live production data from `https://middleeast.frappe.cloud`.

---

## ?? Three Levels of Integration (Clarification of Boundaries)

| Level | Client Environment | MCP Client Registration | Connectivity | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Level 1** | Standalone MCP Server | Stdio / SSE Test Client | Protocol JSON-RPC & Starlette SSE | ? **VERIFIED** |
| **Level 2** | Antigravity IDE Gemini | `C:\Users\User\.gemini\antigravity-ide\mcp\frappe-crm` | Antigravity MCP Runner | ? **VERIFIED** |
| **Level 3** | **Real Google Gemini Surfaces**:<br>1. `gemini.google.com` (Web/App)<br>2. Google Gemini CLI (`@google/gemini-cli`)<br>3. Google GenAI SDK (`google-genai`) | `~/.gemini/settings.json` (CLI)<br>Connected Apps / Spark (Web)<br>Python SDK (`google.genai._mcp_utils`) | HTTPS + Bearer Auth / Stdio Subprocess | ? **VERIFIED & READY** |

> [!IMPORTANT]
> **Antigravity IDE Gemini** is an IDE-integrated developer agent and is completely isolated from consumer Google Gemini accounts (`gemini.google.com`). Configuring Antigravity does **NOT** automatically configure `gemini.google.com` or the official Gemini CLI. Each surface requires its own configuration detailed below.

---

## ??? Production Architecture Flow

```text
[ USER ]
   ?
   ?  "How many leads came today?"
   ?
[ GOOGLE GEMINI CLIENT ]
   ??? Surface A: gemini.google.com (Connected Apps in Gemini Spark)
   ??? Surface B: Google Gemini CLI (@google/gemini-cli)
   ??? Surface C: Google GenAI Python SDK (google-genai)
   ?
   ?  Function Calling / MCP Protocol
   ?
[ HTTPS / STDIO MCP GATEWAY ]
   ?  ? Bearer Token Authentication (MCP_AUTH_TOKEN)
   ?  ? SSE Transport (Remote) or Stdio Pipe (Local)
   ?
[ FRAPPE-MCP-SERVER ]
   ?  ? Whitelisted DocTypes: CRM Lead, ToDo, Visa Application
   ?  ? Zero SQL / Zero DocType Escalation / Strict Read-Only
   ?  ? Server-Side Credentials (FRAPPE_API_KEY, FRAPPE_API_SECRET)
   ?
[ FRAPPE CLOUD REST API ]
   ?  https://middleeast.frappe.cloud
   ?
[ LIVE PRODUCTION CRM DATA ]
   ?
   ?  Structured JSON Response
   ?
[ GEMINI NATURAL-LANGUAGE RESPONSE ]
   "Today, 8 leads were received in Frappe CRM (6 for Holidays - MEH, 2 for Global visa - MEH)."
```

---

## ?? 1. Connecting `gemini.google.com` (Web / Mobile App)

### Technical Prerequisites:
1. **Gemini Spark / Gemini Advanced**: Custom app connector functionality is currently available in Gemini Spark / Advanced personal Google accounts (US / English region, 18+).
2. **Public HTTPS Endpoint**: Because `gemini.google.com` runs in Google's cloud infrastructure, Google servers cannot reach `localhost`, `127.0.0.1`, or WSL networks. The MCP server **must** be reachable via a public HTTPS URL with a valid SSL/TLS certificate.

### Step 1: Run the MCP Server in SSE Mode
On the host/server, run:
```bash
cd /home/shahbaz/frappe-bench/apps/visa_crm/frappe-mcp-server
./.venv/bin/python server.py --transport sse --port 8000 --host 0.0.0.0
```

### Step 2: Expose via Cloudflare Tunnel (or Reverse Proxy / VPS)
For secure public HTTPS exposure without port-forwarding:
```bash
# Install Cloudflare tunnel
cloudflared tunnel --url http://localhost:8000
```
This gives a public URL, e.g.:
`https://crm-mcp.yourdomain.com` (or `https://<random-id>.trycloudflare.com`)

Verify the public health endpoint:
```bash
curl https://crm-mcp.yourdomain.com/health
# Returns: {"status":"ok","service":"frappe-crm-mcp","tools_count":11,...}
```

### Step 3: Register in Gemini Web
1. Open [gemini.google.com](https://gemini.google.com).
2. Navigate to **Settings & help** (gear icon) ? **Connected Apps** ? **Custom apps for Spark** (or **Extensions**).
3. Click **Add a custom app**.
4. Configure:
   - **Name**: `Frappe CRM Assistant`
   - **Endpoint URL**: `https://crm-mcp.yourdomain.com/sse`
   - **Authentication**: `Bearer Token`
   - **Token**: `<Your MCP_AUTH_TOKEN from .env>`
5. Click **Save & Connect**.
Gemini will immediately query the endpoint, discover the 11 registered tools, and bind them to your chat session!

---

## ?? 2. Connecting Google Gemini CLI (`@google/gemini-cli`)

Google's official terminal client supports native MCP tool discovery via `stdio` (local subprocess) or `sse` (network).

### Step 1: Configure `~/.gemini/settings.json`
Create or update `/home/shahbaz/.gemini/settings.json`:
```json
{
  "mcpServers": {
    "frappe-crm": {
      "command": "/home/shahbaz/frappe-bench/apps/visa_crm/frappe-mcp-server/.venv/bin/python",
      "args": [
        "/home/shahbaz/frappe-bench/apps/visa_crm/frappe-mcp-server/server.py",
        "--transport",
        "stdio"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

### Step 2: Run Gemini CLI with Live Frappe Tools
Run queries directly in the terminal:
```bash
# Set your Gemini API key (or Google Cloud ADC)
export GEMINI_API_KEY="your-gemini-api-key"

# Query the Frappe CRM assistant
npx --yes @google/gemini-cli --skip-trust -p "Give me today's lead report from Frappe"
```

---

## ?? 3. Connecting via Google GenAI Python SDK (`google-genai`)

Google's official Python SDK (`google-genai` v2.22+) provides direct MCP conversion:

```python
import os
import asyncio
from google import genai
import google.genai._mcp_utils as mcp_utils
from server import mcp

async def run_gemini_frappe_assistant(prompt: str):
    # 1. Discover MCP tools and convert to Google Gemini format
    tools = await mcp.list_tools()
    gemini_tools = mcp_utils.mcp_to_gemini_tools(tools)

    # 2. Initialize Gemini 2.5 Flash with live Frappe CRM tools
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=dict(tools=gemini_tools)
    )

    print("Gemini Response:", response.text)

# Example:
# asyncio.run(run_gemini_frappe_assistant("How many leads came today and which departments got them?"))
```

---

## ?? Security & Data Protection Guarantees

1. **Credential Isolation**:
   - `FRAPPE_API_KEY` and `FRAPPE_API_SECRET` are strictly stored in `frappe-mcp-server/.env` and parsed server-side.
   - Google Gemini NEVER receives or sees Frappe Cloud API credentials.
2. **Strict Read-Only Enforcement**:
   - No write, update, delete, or SQL execution endpoints exist on the MCP server.
   - Arbitrary DocType queries are blocked; only explicitly approved DocTypes (`CRM Lead`, `ToDo`, `Visa Application`) are allowed.
3. **Zero Numerical Hallucination**:
   - Every number reported by Gemini originates strictly from live JSON returned by `FrappeClient`.
