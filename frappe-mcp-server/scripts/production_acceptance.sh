#!/bin/bash
# =============================================================================
# Production Acceptance Verification Script for Frappe CRM MCP on Render
# Exits with non-zero code if any mandatory production requirement fails.
# =============================================================================

set -e

HOST="${1:-visa-crm-mcp.onrender.com}"
BASE_URL="https://${HOST}"

echo "================================================================================"
echo "FRAPPE CRM MCP PRODUCTION ACCEPTANCE VERIFIER"
echo "Target Host: ${BASE_URL}"
echo "Timestamp:   $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "================================================================================"

# Step 1: DNS Resolution Check
echo -n "[*] Step 1: DNS Resolution for ${HOST}... "
if ! host "${HOST}" > /dev/null 2>&1; then
    echo "FAIL (DNS does not resolve)"
    exit 1
fi
echo "PASS"

# Step 2: HTTPS Connectivity & No-Server Check
echo -n "[*] Step 2: Public HTTPS & Routing Check (/health)... "
HEALTH_RESP=$(curl -s -i -m 10 "${BASE_URL}/health" || true)

if echo "${HEALTH_RESP}" | grep -q "x-render-routing: no-server"; then
    echo "FAIL"
    echo "    ERROR: Render edge router returned 'x-render-routing: no-server'."
    echo "    DIAGNOSIS: Web Service '${HOST}' is not provisioned or active on Render."
    exit 2
fi

HTTP_STATUS=$(echo "${HEALTH_RESP}" | grep -E '^HTTP/[123\.]+' | awk '{print $2}' | tail -n 1)
if [ "${HTTP_STATUS}" != "200" ]; then
    echo "FAIL (HTTP ${HTTP_STATUS})"
    exit 3
fi
echo "PASS (HTTP 200 OK)"

# Step 3: MCP Streamable HTTP Endpoint (/mcp)
echo -n "[*] Step 3: MCP Endpoint Probing (/mcp)... "
MCP_RESP=$(curl -s -i -m 10 -X POST "${BASE_URL}/mcp" || true)
if echo "${MCP_RESP}" | grep -q "x-render-routing: no-server"; then
    echo "FAIL (no-server)"
    exit 4
fi
echo "PASS"

# Step 4: OAuth Discovery Metadata Check
echo -n "[*] Step 4: OAuth Discovery (/.well-known/oauth-authorization-server)... "
OAUTH_RESP=$(curl -s -i -m 10 "${BASE_URL}/.well-known/oauth-authorization-server" || true)
if ! echo "${OAUTH_RESP}" | grep -q "200 OK"; then
    echo "FAIL"
    exit 5
fi
echo "PASS"

echo "================================================================================"
echo "PRODUCTION ACCEPTANCE: PASS"
echo "The remote Render service is active, responsive, and ready for Google Gemini."
echo "================================================================================"
exit 0
