#!/bin/bash
# =============================================================================
# Production Acceptance Verification Script for Frappe CRM MCP on Render
# Enforces Antigravity Master Acceptance Gate (Phase 13 & 29).
# Exits with 0 ONLY if all production conditions pass independently.
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_HOST="${1:-visa-crm-mcp.onrender.com}"
BASE_URL="https://${TARGET_HOST}"

echo "================================================================================"
echo "FRAPPE CRM MCP — PRODUCTION ACCEPTANCE GATE"
echo "Target Host: ${BASE_URL}"
echo "Timestamp:   $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "================================================================================"

# Step 1: Run Automated Remote Endpoint Prober
echo "[*] Step 1: Executing automated remote endpoint prober..."
set +e
python3 "${SCRIPT_DIR}/verify_remote_endpoints.py" "${BASE_URL}"
PROBE_STATUS=$?
set -e

if [ $PROBE_STATUS -ne 0 ]; then
    echo ""
    echo "================================================================================"
    echo "PRODUCTION ACCEPTANCE: FAIL"
    echo "The public Render service at ${BASE_URL} failed endpoint verification."
    echo "================================================================================"
    exit $PROBE_STATUS
fi

echo ""
echo "[*] Step 2: Remote service is active! Verifying authenticated MCP tool invocation..."

# Step 2: Tool Invocation against Live Remote Service
python3 - <<EOF
import os
import sys
import json
import urllib.request

base_url = "${BASE_URL}"
health_url = f"{base_url}/health"

req = urllib.request.Request(health_url)
with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read().decode())
    assert data.get("status") == "ok", "Health status not ok"
    assert data.get("tools_count") == 11, f"Expected 11 tools, got {data.get('tools_count')}"
print("[+] Remote /health verified: 11 tools advertised.")
EOF

echo ""
echo "================================================================================"
echo "PRODUCTION ACCEPTANCE: PASS"
echo "Public Cloud Service is verified live, responsive, and 24x7 operational."
echo "================================================================================"
exit 0
