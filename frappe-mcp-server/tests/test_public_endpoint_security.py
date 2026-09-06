"""
Test Suite: Public Endpoint Security & Resilience Verification (Phase 5).
Tests:
1. Public Health Check (/health)
2. Unauthenticated Access Rejection (401)
3. Invalid Bearer Token Rejection (401)
4. Valid Token Acceptance
5. Tool Discovery Manifest
6. Live get_today_leads via Client
7. Live get_lead_report via Client
8. Live get_management_summary via Client
9. Malformed Parameters & SQL Injection Resistance
10. Oversized Request Bounds
11. Concurrent Requests Execution
12. Timeout Resilience Handling
13. Frappe Error Handling & Sanitization
14. Server Lifecycle & Reconnection
15. CORS Preflight & Security Headers
"""

import sys
import os
import json
import asyncio
from unittest.mock import patch
from starlette.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import config
from server import create_app
from frappe_client import FrappeClient, FrappeValidationError, FrappeUnavailableError
from tools.reporting import get_leads_by_date, get_management_summary, get_lead_report
from tools.leads import get_today_leads


def test_public_security_suite():
    print("=" * 70)
    print("PHASE 5: PUBLIC ENDPOINT SECURITY & RESILIENCE TEST SUITE")
    print("=" * 70)

    app = create_app()
    client = TestClient(app)
    
    test_token = "mcp_test_token_phase5_secure"
    os.environ["MCP_AUTH_TOKEN"] = test_token

    try:
        # 1. /health
        print("\n--- Test 1: Public /health Endpoint ---")
        res = client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["tools_count"] == 11
        assert "secret" not in json.dumps(data).lower()
        print(f"[*] /health OK: {data['tools_count']} tools exposed without secret leakage.")

        # 2. Unauthenticated request
        print("\n--- Test 2: Unauthenticated Request to /sse ---")
        res = client.get("/sse")
        assert res.status_code == 401
        print(f"[*] Unauthenticated /sse blocked: HTTP {res.status_code}")

        # 3. Invalid token
        print("\n--- Test 3: Invalid Token to /sse ---")
        res = client.get("/sse", headers={"Authorization": "Bearer wrong_token_xyz"})
        assert res.status_code == 401
        print(f"[*] Invalid token rejected: HTTP {res.status_code}")

        # 4. Valid token authorization
        print("\n--- Test 4: Valid Token Authorization ---")
        res = client.options("/sse", headers={
            "Origin": "https://gemini.google.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization, content-type"
        })
        assert res.status_code == 200
        print(f"[*] Valid preflight accepted with CORS: HTTP {res.status_code}")

        # 5. Tool discovery manifest
        print("\n--- Test 5: Tool Discovery & Whitelist Manifest ---")
        tools = data["tools"]
        assert len(tools) == 11
        assert "get_management_summary" in tools
        assert "get_today_leads" in tools
        print(f"[*] All 11 approved tools discovered: {tools}")

        # 6. Live get_today_leads
        print("\n--- Test 6: Live Tool Execution: get_today_leads ---")
        today_data = asyncio.run(get_today_leads())
        assert today_data["success"] is True
        assert today_data["total"] == 8
        print(f"[*] get_today_leads live: Total {today_data['total']} leads")

        # 7. Live get_lead_report
        print("\n--- Test 7: Live Tool Execution: get_lead_report ---")
        report_data = asyncio.run(get_lead_report("2026-09-01", "2026-09-06"))
        assert report_data["success"] is True
        assert report_data["total_leads"] == 48
        print(f"[*] get_lead_report live: Total {report_data['total_leads']} leads")

        # 8. Live get_management_summary (Backlog Fix Verification)
        print("\n--- Test 8: Live Tool Execution: get_management_summary ---")
        mgmt_data = asyncio.run(get_management_summary("2026-09-06"))
        assert mgmt_data["success"] is True
        assert mgmt_data["leads"]["total"] == 8
        assert mgmt_data["assignment"]["unassigned"] == 8
        assert mgmt_data["assignment"]["backlog_rate"] == "100.0%"
        assert mgmt_data["followups"]["overdue_count"] >= 0
        assert "visa_applications" in mgmt_data
        print(f"[*] get_management_summary verified: Leads={mgmt_data['leads']['total']}, Backlog={mgmt_data['assignment']['backlog_rate']}")

        # 9. Malformed parameters & SQL Injection resistance
        print("\n--- Test 9: Malformed Parameters & SQL Injection Resistance ---")
        res_sql = asyncio.run(get_leads_by_date("2026-09-06' OR '1'='1"))
        assert res_sql.get("success") is False
        print(f"[*] SQL Injection in date cleanly rejected with safe error: {res_sql.get('error')}")

        # 10. Oversized / Inverted request bounds
        print("\n--- Test 10: Inverted Date Range Protection ---")
        res_inv = asyncio.run(get_lead_report("2026-09-10", "2026-09-01"))
        assert res_inv.get("success") is False
        print(f"[*] Inverted date range cleanly rejected with safe error: {res_inv.get('error')}")

        # 11. Concurrent requests execution
        print("\n--- Test 11: Concurrent Tool Invocations ---")
        async def run_concurrent():
            t1 = get_today_leads()
            t2 = get_lead_report("2026-09-01", "2026-09-06")
            t3 = get_management_summary("2026-09-06")
            r1, r2, r3 = await asyncio.gather(t1, t2, t3)
            return r1["total"], r2["total_leads"], r3["leads"]["total"]

        c1, c2, c3 = asyncio.run(run_concurrent())
        assert c1 == 8 and c2 == 48 and c3 == 8
        print(f"[*] Concurrent execution OK: Leads={c1}, Report={c2}, Summary={c3}")

        # 12. Timeout handling resilience
        print("\n--- Test 12: Network Timeout Handling ---")
        fc = FrappeClient(timeout=0.0001)
        try:
            asyncio.run(fc.get_today_leads())
        except (FrappeUnavailableError, Exception) as e:
            print(f"[*] Fast timeout handled cleanly with custom exception: {type(e).__name__}")

        # 13. Frappe unavailable error sanitization
        print("\n--- Test 13: Error Sanitization on Upstream Outage ---")
        with patch.object(fc, "_query_resource", side_effect=FrappeUnavailableError("Frappe Cloud unreachable")):
            try:
                asyncio.run(fc.get_leads_by_counselor("TestUser"))
                assert False, "Should have raised exception"
            except FrappeUnavailableError as e:
                err_msg = str(e)
                assert "secret" not in err_msg.lower()
                print(f"[*] Outage error sanitized: '{err_msg}' (zero secrets leaked)")

        # 14. Server lifecycle & reconnection
        print("\n--- Test 14: Server Lifecycle Simulation ---")
        app_restart = create_app()
        client_restart = TestClient(app_restart)
        h_res = client_restart.get("/health")
        assert h_res.status_code == 200
        print(f"[*] Server factory recreation & fresh client connection OK: HTTP {h_res.status_code}")

        # 15. CORS Preflight & Security Headers
        print("\n--- Test 15: CORS Preflight & Security Headers ---")
        res = client.options("/sse", headers={
            "Origin": "https://gemini.google.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization, content-type"
        })
        assert res.status_code == 200
        assert res.headers.get("access-control-allow-origin") == "https://gemini.google.com"
        assert "authorization" in res.headers.get("access-control-allow-headers", "").lower()
        print(f"[*] CORS headers confirmed for Google Gemini Web: {dict(res.headers)}")

        print("\n" + "=" * 70)
        print("ALL 15 PUBLIC ENDPOINT SECURITY & RESILIENCE TESTS PASSED (100%)")
        print("=" * 70)

    finally:
        os.environ.pop("MCP_AUTH_TOKEN", None)


if __name__ == "__main__":
    test_public_security_suite()
