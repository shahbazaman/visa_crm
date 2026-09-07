# =============================================================================
# [DEPRECATED — LOCAL DEVELOPMENT ONLY]
# Production MCP runs 24x7 in the cloud (Render / Cloud Run).
# Do NOT run this script for production Google Gemini operation.
# =============================================================================
#!/bin/bash
# Starts Frappe MCP Server and Cloudflare Quick Tunnel in background

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR" || exit 1

# Check if already running
if [ -f "$APP_DIR/.server.pid" ] && kill -0 "$(cat "$APP_DIR/.server.pid")" 2>/dev/null; then
    echo "[!] MCP Server is already running (PID $(cat "$APP_DIR/.server.pid"))"
else
    echo "[*] Starting Frappe MCP Server on 127.0.0.1:8000..."
    nohup "$APP_DIR/.venv/bin/python" server.py --transport http --host 127.0.0.1 --port 8000 > "$APP_DIR/server.log" 2>&1 &
    echo $! > "$APP_DIR/.server.pid"
    echo "[+] Server started (PID $(cat "$APP_DIR/.server.pid"))"
fi

sleep 2

if [ -f "$APP_DIR/.tunnel.pid" ] && kill -0 "$(cat "$APP_DIR/.tunnel.pid")" 2>/dev/null; then
    echo "[!] Cloudflare tunnel is already running (PID $(cat "$APP_DIR/.tunnel.pid"))"
else
    echo "[*] Starting Cloudflare Tunnel..."
    nohup /home/shahbaz/.local/bin/cloudflared tunnel --url http://127.0.0.1:8000 > "$APP_DIR/tunnel.log" 2>&1 &
    echo $! > "$APP_DIR/.tunnel.pid"
    echo "[+] Tunnel started (PID $(cat "$APP_DIR/.tunnel.pid"))"
fi

sleep 4
TUNNEL_URL=$(grep -o 'https://[a-zA-Z0-9.-]*\.trycloudflare\.com' "$APP_DIR/tunnel.log" | tail -n 1)

echo ""
echo "================================================================"
echo " Frappe MCP Server & Cloudflare Tunnel Active"
echo "================================================================"
echo " Public MCP URL: ${TUNNEL_URL}/mcp"
echo " Health Check:   ${TUNNEL_URL}/health"
echo " Stop command:   ./stop_tunnel.sh"
echo "================================================================"
