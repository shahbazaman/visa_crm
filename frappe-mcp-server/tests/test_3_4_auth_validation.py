"""
Test 3 & 4: Authentication Verification & Invalid Auth Rejection.
- Test 3: Valid credentials return production data.
- Test 4: Invalid credentials are rejected cleanly without leaking secrets.
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import config
from frappe_client import FrappeClient, FrappeAuthError


async def run_test_4_invalid_auth():
    print("\n--- Running Test 4: Invalid Authentication Rejection ---")
    # Test with bogus credentials
    dummy_client = FrappeClient(
        base_url=config.frappe_base_url,
        api_key="invalid_dummy_key",
        api_secret="invalid_dummy_secret",
    )
    
    try:
        await dummy_client.get_today_leads()
        print("[FAIL] Invalid credentials were not rejected!")
        sys.exit(1)
    except FrappeAuthError as exc:
        assert str(exc) == "Frappe CRM authentication failed.", f"Unexpected error text: {exc}"
        # Critical security check: ensure no secret tokens or keys in error output
        assert "dummy" not in str(exc).lower(), "Sensitive strings leaked in exception message!"
        assert "token" not in str(exc).lower(), "Auth token scheme leaked in exception message!"
        print(f"[*] Invalid authentication rejected properly with safe message: '{exc}'")
        print("[*] Security Check Passed: No credentials or tokens exposed.")
        print("[RESULT] Test 4: Invalid Authentication: PASS")


async def run_test_3_valid_auth():
    print("\n--- Running Test 3: Valid Authentication Verification ---")
    if not config.is_configured:
        print("[!] Credentials not configured in .env. Skipping Test 3 until credentials are set.")
        print("[INFO] Please configure FRAPPE_API_KEY and FRAPPE_API_SECRET in frappe-mcp-server/.env")
        return False
        
    print(f"[*] Authenticating with configured API Key: {config.mask_key(config.frappe_api_key)}")
    valid_client = FrappeClient()
    
    try:
        data = await valid_client.get_today_leads()
        assert data.get("success") is True, f"Response success not True: {data}"
        print(f"[*] Valid authentication succeeded! Returned {data.get('total')} production CRM leads.")
        print("[RESULT] Test 3: Valid Authentication: PASS")
        return True
    except Exception as exc:
        print(f"[FAIL] Valid authentication request failed: {exc}")
        sys.exit(1)


async def main():
    print("=== Test 3 & 4: Authentication Verification Suite ===")
    
    # Run Test 4 first (always executable without credentials)
    await run_test_4_invalid_auth()
    
    # Run Test 3 (requires credentials)
    await run_test_3_valid_auth()


if __name__ == "__main__":
    asyncio.run(main())
