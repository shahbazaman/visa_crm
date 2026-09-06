# Production Cloudflare Named Tunnel & Systemd Architecture

This guide details the production architecture to transition from an ephemeral `trycloudflare.com` tunnel to a permanent, enterprise-grade deployment with custom domain routing and high availability.

---

## 1. Production Architecture Overview

```text
Google Gemini Web / App
         ?
         ? (HTTPS)
https://crm-mcp.yourdomain.com
         ?
         ? (Cloudflare Anycast Global Edge)
Cloudflare Named Tunnel
         ?
         ? (Encrypted QUIC / HTTP/2 outbound tunnel)
Local MCP Server Host (127.0.0.1:8000)
         ?
         ? (Loopback ASGI)
server.py (Uvicorn + FastMCP)
         ?
         ? (Server-Side HTTPS REST)
https://middleeast.frappe.cloud
```

---

## 2. Step 1: Create a Persistent Cloudflare Named Tunnel

```bash
# 1. Login to your Cloudflare account
cloudflared tunnel login

# 2. Create a named tunnel
cloudflared tunnel create crm-mcp-production
# Note: This outputs a Tunnel ID (e.g. 7a123456-abcd-ef01-2345-6789abcdef01) and saves credentials to ~/.cloudflared/<TUNNEL_ID>.json

# 3. Create the configuration file (~/.cloudflared/config.yml)
cat << 'EOF' > ~/.cloudflared/config.yml
tunnel: <YOUR_TUNNEL_ID>
credentials-file: /home/shahbaz/.cloudflared/<YOUR_TUNNEL_ID>.json

ingress:
  - hostname: crm-mcp.yourdomain.com
    service: http://127.0.0.1:8000
    originRequest:
      connectTimeout: 30s
      noTLSVerify: false
  - service: http_status:404
EOF

# 4. Route your custom DNS subdomain to the tunnel
cloudflared tunnel route dns crm-mcp-production crm-mcp.yourdomain.com
```

---

## 3. Step 2: Configure Systemd Services for High Availability

### Service 1: Frappe CRM MCP Server (`/etc/systemd/system/frappe-mcp.service`)
```ini
[Unit]
Description=Frappe CRM FastMCP Server (ASGI)
After=network.target

[Service]
Type=simple
User=shahbaz
WorkingDirectory=/home/shahbaz/frappe-bench/apps/visa_crm/frappe-mcp-server
ExecStart=/home/shahbaz/frappe-bench/apps/visa_crm/frappe-mcp-server/.venv/bin/python server.py --transport sse --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5s
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Service 2: Cloudflare Tunnel Service (`/etc/systemd/system/cloudflared-mcp.service`)
```ini
[Unit]
Description=Cloudflare Tunnel for Frappe CRM MCP
After=network.target frappe-mcp.service

[Service]
Type=simple
User=shahbaz
ExecStart=/home/shahbaz/.local/bin/cloudflared tunnel --config /home/shahbaz/.cloudflared/config.yml run
Restart=always
RestartSec=5s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Enable & Start Services:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now frappe-mcp
sudo systemctl enable --now cloudflared-mcp
```

---

## 4. Step 3: Security & Operational Hardening

1. **Token Rotation**:
   - Update `MCP_AUTH_TOKEN` in `.env`.
   - Run `sudo systemctl restart frappe-mcp`.
   - Update the token in Gemini Web Connected Apps settings.
2. **Emergency Cutoff**:
   - To immediately terminate all external AI access without affecting Frappe CRM:
     ```bash
     sudo systemctl stop cloudflared-mcp
     ```
3. **Monitoring & Health Checks**:
   - Configure UptimeRobot or Datadog to poll `GET https://crm-mcp.yourdomain.com/health` every 60 seconds (Expected: 200 OK, `tools_count: 11`).
