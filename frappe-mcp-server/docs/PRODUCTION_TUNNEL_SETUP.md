> [!WARNING]
> **DEPRECATED — LOCAL TUNNEL ARCHITECTURE (DEVELOPMENT ONLY)**
> This document describes local Cloudflare tunnels, which require an active local computer.
> For true 24x7 always-on operation without keeping your PC powered on, refer to:
> [`RENDER_DEPLOYMENT_GUIDE.md`](./RENDER_DEPLOYMENT_GUIDE.md)

# Production Cloudflare Tunnel & Systemd Setup

This guide details setting up a permanent Cloudflare Named Tunnel and systemd services for 24/7 autonomous production operation.

---

## 1. Prerequisites

- Cloudflare account with a custom domain (e.g. `<YOUR_DOMAIN>`).
- `cloudflared` CLI installed at `/home/shahbaz/.local/bin/cloudflared`.

---

## 2. Cloudflare Named Tunnel Setup

### Step 1: Log in to Cloudflare
```bash
/home/shahbaz/.local/bin/cloudflared tunnel login
```

### Step 2: Create Named Tunnel
```bash
/home/shahbaz/.local/bin/cloudflared tunnel create frappe-crm-mcp
```
This outputs a `<TUNNEL_ID>` and creates `~/.cloudflared/<TUNNEL_ID>.json`.

### Step 3: Route DNS Subdomain
```bash
/home/shahbaz/.local/bin/cloudflared tunnel route dns frappe-crm-mcp crm-mcp.<YOUR_DOMAIN>
```

### Step 4: Configure `config/cloudflared-mcp.yml`
Edit `/home/shahbaz/frappe-bench/apps/visa_crm/frappe-mcp-server/config/cloudflared-mcp.yml`:
```yaml
tunnel: <TUNNEL_ID>
credentials-file: /home/shahbaz/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: crm-mcp.<YOUR_DOMAIN>
    service: http://127.0.0.1:8000
  - service: http_status:404
```

### Step 5: Update `.env`
Set the public domain in `/home/shahbaz/frappe-bench/apps/visa_crm/frappe-mcp-server/.env`:
```env
MCP_PUBLIC_URL=https://crm-mcp.<YOUR_DOMAIN>
```

---

## 3. Systemd Production Services

Install and enable the systemd services:

```bash
sudo cp /home/shahbaz/frappe-bench/apps/visa_crm/frappe-mcp-server/services/frappe-mcp.service /etc/systemd/system/
sudo cp /home/shahbaz/frappe-bench/apps/visa_crm/frappe-mcp-server/services/cloudflared-mcp.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now frappe-mcp.service
sudo systemctl enable --now cloudflared-mcp.service
```

### Verify Service Status:
```bash
sudo systemctl status frappe-mcp.service
sudo systemctl status cloudflared-mcp.service
```

### View Live Logs:
```bash
journalctl -u frappe-mcp.service -f
journalctl -u cloudflared-mcp.service -f
```
