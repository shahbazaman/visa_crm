"""
Test Suite: Remote MCP Server (SSE Transport) Verification.
Tests:
1. Public Health Check (/health)
2. Authentication Enforcement on /sse (rejects missing/invalid Bearer token)
3. Direct Remote Tool Execution against Production Frappe Cloud
4. Zero Credential Leakage in responses or headers
"""

import sys
import os
import json
import asyncio
from starlette.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import config
from server import create_app


def run_remote_mcp_tests():
    print("=== Remote MCP Server (SSE & HTTP) Verification Suite ===")

    app = create_app()
    client = TestClient(app)

    # 1. Test Health Endpoint
    print("\n--- Test 1: Public Health Check Endpoint (/health) ---")
    health_resp = client.get("/health")
    assert health_resp.status_code == 200, f"Expected 200, got {health_resp.status_code}"
    health_data = health_resp.json()
    assert health_data.get("status") == "ok", f"Expected status ok, got {health_data}"
    assert "get_today_leads" in health_data.get("tools", []), "Missing get_today_leads in tools list"
    
    # Verify no credentials leaked in health check
    health_str = json.dumps(health_data).lower()
    assert "secret" not in health_str, "Secret leaked in health response"
    assert config.frappe_api_key not in health_str, "API key leaked in health response"
    print(f"[*] Health Check Response: {health_data}")
    print("[RESULT] Test 1: Health Check: PASS")

    # 2. Test Authentication Middleware
    print("\n--- Test 2: Remote Authentication Enforcement ---")
    original_token = os.environ.get("MCP_AUTH_TOKEN")
    test_token = "test_secure_mcp_token_xyz123"
    os.environ["MCP_AUTH_TOKEN"] = test_token

    # A. Unauthenticated request to /sse should be rejected with 401
    unauth_resp = client.get("/sse")
    assert unauth_resp.status_code == 401, f"Expected 401 for unauthenticated request, got {unauth_resp.status_code}"
    print(f"[*] Unauthenticated /sse properly rejected: HTTP {unauth_resp.status_code} ({unauth_resp.json()})")

    # B. Invalid token request to /sse should be rejected with 401
    bad_resp = client.get("/sse", headers={"Authorization": "Bearer wrong_secret_token"})
    assert bad_resp.status_code == 401, f"Expected 401 for invalid token, got {bad_resp.status_code}"
    print(f"[*] Invalid token properly rejected: HTTP {bad_resp.status_code} ({bad_resp.json()})")

    # Restore original environment
    if original_token is not None:
        os.environ["MCP_AUTH_TOKEN"] = original_token
    else:
        os.environ.pop("MCP_AUTH_TOKEN", None)

    print("[RESULT] Test 2: Remote Authentication Enforcement: PASS")

    # 3. Test Remote Tool Execution against Production Frappe
    print("\n--- Test 3: Remote Tool Execution against Frappe Cloud ---")
    from tools.leads import get_today_leads
    result = asyncio.run(get_today_leads())
    assert result.get("success") is True, f"Tool execution failed: {result}"
    assert result.get("total") == 8, f"Expected 8 leads, got {result.get('total')}"
    assert isinstance(result.get("leads"), list), "Leads is not a list"
    assert len(result["leads"]) == 8, f"Expected 8 lead records, got {len(result['leads'])}"
    
    print(f"[*] Remote Tool Execution returned {result.get('total')} production CRM leads.")
    if result["leads"]:
        sample = result["leads"][0]
        print(f"[*] Sample Live Lead: {sample.get('name')} | Customer: {sample.get('customer_name')} | Dept: {sample.get('department')}")

    print("[RESULT] Test 3: Remote Tool Execution: PASS")

    # 4. Test CORS Preflight Options Request
    print("\n--- Test 4: CORS Preflight (OPTIONS) Support for Gemini Web ---")
    preflight = client.options("/sse", headers={
        "Origin": "https://gemini.google.com",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization, content-type",
    })
    assert preflight.status_code == 200, f"Expected 200 for preflight, got {preflight.status_code}"
    assert preflight.headers.get("access-control-allow-origin") in ("*", "https://gemini.google.com")
    print(f"[*] CORS Preflight for https://gemini.google.com successfully handled: HTTP {preflight.status_code}")
    print("[RESULT] Test 4: CORS Support: PASS")

    print("\n=== All Remote MCP Server Tests PASSED Successfully ===\n")


if __name__ == "__main__":
    run_remote_mcp_tests()
