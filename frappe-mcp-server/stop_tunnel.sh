# =============================================================================
# [DEPRECATED — LOCAL DEVELOPMENT ONLY]
# Helper to stop local dev background processes.
# =============================================================================
#!/bin/bash
# Stops Frappe MCP Server and Cloudflare Tunnel

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$APP_DIR/.server.pid" ]; then
    PID=$(cat "$APP_DIR/.server.pid")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        echo "[+] Stopped MCP Server (PID $PID)"
    fi
    rm -f "$APP_DIR/.server.pid"
fi

if [ -f "$APP_DIR/.tunnel.pid" ]; then
    PID=$(cat "$APP_DIR/.tunnel.pid")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        echo "[+] Stopped Cloudflare Tunnel (PID $PID)"
    fi
    rm -f "$APP_DIR/.tunnel.pid"
fi

# Cleanup any stray uvicorn or cloudflared instances
pkill -f "python server.py --transport http" 2>/dev/null
pkill -f "cloudflared tunnel --url http://127.0.0.1:8000" 2>/dev/null

echo "[+] All Frappe MCP services stopped."
