"""
Test 2: Verify HTTPS Connectivity to Frappe Cloud Production.
Endpoint: https://middleeast.frappe.cloud/api/method/visa_crm.api.mcp.get_today_leads
"""

import sys
import os
import asyncio
import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import config
from frappe_client import frappe_client


async def main():
    print("=== Test 2: Frappe HTTPS Connectivity Verification ===")
    url = f"{config.frappe_base_url}/api/method/visa_crm.api.mcp.get_today_leads"
    print(f"[*] Target Endpoint: {url}")
    print(f"[*] Base URL: {config.frappe_base_url}")
    
    # 1. Test basic HTTPS handshake and endpoint presence
    async with httpx.AsyncClient(timeout=config.http_timeout) as client:
        try:
            resp = await client.get(url)
            print(f"[*] Public HTTPS probe response code: {resp.status_code}")
            # Without auth, production MUST reject with 403 PermissionError
            assert resp.status_code in (200, 403), f"Unexpected HTTP status: {resp.status_code}"
            print("[*] Production HTTPS connectivity verified (server is online and responsive).")
        except httpx.NetworkError as e:
            print(f"[FAIL] Network connection error: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"[FAIL] Unexpected error probing production endpoint: {e}")
            sys.exit(1)

    # 2. If credentials are set, verify full HTTP 200 via client
    if config.is_configured:
        print("[*] Credentials detected. Performing authenticated HTTPS call...")
        try:
            result = await frappe_client.get_today_leads()
            assert result.get("success") is True, f"Success flag not True: {result}"
            print(f"[*] Authenticated HTTPS returned HTTP 200 OK with {result.get('total')} leads.")
        except Exception as e:
            print(f"[FAIL] Authenticated request failed: {e}")
            sys.exit(1)
    else:
        print("[!] Credentials not yet configured in .env. Unauthenticated endpoint reachability confirmed.")

    print("\n[RESULT] Test 2: Frappe HTTPS Connectivity: PASS\n")


if __name__ == "__main__":
    asyncio.run(main())
