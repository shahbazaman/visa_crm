"""
Test Suite: Stage A Lead Reporting Tools (Phase 3).
Validates all Stage A MCP tools against live production Frappe Cloud and edge cases.
"""

import asyncio
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import config
from frappe_client import FrappeClient, FrappeValidationError, FrappeAuthError
from tools.reporting import (
    get_leads_by_date,
    get_lead_report,
    get_leads_by_department,
    get_leads_by_counselor,
    get_lead_sources,
    get_unassigned_leads,
)
from tools.leads import get_today_leads


class TestStageALeadReportingTools(unittest.TestCase):
    """Test suite for Stage A lead reporting capabilities."""

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    # -------------------------------------------------------------------------
    # 1. get_today_leads (Regression verification)
    # -------------------------------------------------------------------------
    def test_01_get_today_leads_live(self):
        print("\n--- Testing Tool 1: get_today_leads ---")
        result = self.loop.run_until_complete(get_today_leads())
        self.assertTrue(result.get("success"), f"Expected success=True, got: {result}")
        self.assertIn("total", result)
        self.assertIn("leads", result)
        self.assertIsInstance(result["leads"], list)
        print(f"[*] get_today_leads succeeded: Total={result['total']}")
        if result["leads"]:
            sample = result["leads"][0]
            print(f"[*] Sample Lead: Name={sample.get('name')}, Dept={sample.get('department')}")
            self.assertIn("name", sample)
            self.assertIn("department", sample)

    # -------------------------------------------------------------------------
    # 2. get_leads_by_date
    # -------------------------------------------------------------------------
    def test_02_get_leads_by_date_valid(self):
        print("\n--- Testing Tool 2: get_leads_by_date (Valid Date) ---")
        result = self.loop.run_until_complete(get_leads_by_date("2026-09-06"))
        self.assertTrue(result.get("success"), f"Expected success=True, got: {result}")
        self.assertEqual(result.get("date"), "2026-09-06")
        self.assertEqual(result.get("total"), 8, "Expected 8 leads for 2026-09-06 on production")
        self.assertEqual(len(result.get("leads")), 8)
        print(f"[*] Leads for 2026-09-06 verified: {result['total']} leads.")

    def test_03_get_leads_by_date_invalid_formats(self):
        print("\n--- Testing Tool 2: get_leads_by_date (Invalid Date Rejections) ---")
        invalid_dates = [
            "invalid-date",
            "2026/09/06",
            "06-09-2026",
            "2026-13-45",
            "2026-09-06'; DROP TABLE tabLead; --",
            "",
            "yesterday",
        ]
        for bad_date in invalid_dates:
            result = self.loop.run_until_complete(get_leads_by_date(bad_date))
            self.assertFalse(result.get("success"), f"Should fail for '{bad_date}'")
            self.assertIn("error", result)
            self.assertNotIn("DROP TABLE", str(result))
            print(f"[*] Correctly rejected bad date '{bad_date}': {result['error']}")

    def test_04_get_leads_by_date_empty_result(self):
        print("\n--- Testing Tool 2: get_leads_by_date (Empty Day) ---")
        result = self.loop.run_until_complete(get_leads_by_date("2020-01-01"))
        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("total"), 0)
        self.assertEqual(result.get("leads"), [])
        print("[*] Correctly handled date with 0 leads without error.")

    # -------------------------------------------------------------------------
    # 3. get_lead_report
    # -------------------------------------------------------------------------
    def test_05_get_lead_report_valid(self):
        print("\n--- Testing Tool 3: get_lead_report (Valid Date Range) ---")
        result = self.loop.run_until_complete(get_lead_report("2026-09-01", "2026-09-06"))
        self.assertTrue(result.get("success"), f"Expected success=True, got: {result}")
        self.assertIn("total_leads", result)
        self.assertIn("leads_by_department", result)
        self.assertIn("leads_by_source", result)
        self.assertIn("leads_by_status", result)
        self.assertIn("assigned_vs_unassigned", result)
        print(f"[*] Lead Report 2026-09-01 to 2026-09-06:")
        print(f"    Total Leads: {result['total_leads']}")
        print(f"    Departments: {result['leads_by_department']}")
        print(f"    Sources: {result['leads_by_source']}")
        print(f"    Assigned vs Unassigned: {result['assigned_vs_unassigned']}")
        self.assertGreaterEqual(result["total_leads"], 8)

    def test_06_get_lead_report_invalid_range(self):
        print("\n--- Testing Tool 3: get_lead_report (Malformed Date Range) ---")
        # start_date > end_date
        result = self.loop.run_until_complete(get_lead_report("2026-09-10", "2026-09-01"))
        self.assertFalse(result.get("success"))
        self.assertIn("error", result)
        print(f"[*] Correctly rejected inverted date range: {result['error']}")

    # -------------------------------------------------------------------------
    # 4. get_leads_by_department
    # -------------------------------------------------------------------------
    def test_07_get_leads_by_department_valid(self):
        print("\n--- Testing Tool 4: get_leads_by_department (Holidays - MEH) ---")
        result = self.loop.run_until_complete(get_leads_by_department("Holidays - MEH"))
        self.assertTrue(result.get("success"), f"Expected success=True, got: {result}")
        self.assertGreater(result.get("total"), 0)
        self.assertEqual(result.get("department"), "Holidays - MEH")
        print(f"[*] Leads for Holidays - MEH: Total={result['total']}")
        first_lead = result["leads"][0]
        self.assertIn("Holidays", first_lead.get("department", ""))

    def test_08_get_leads_by_department_fuzzy(self):
        print("\n--- Testing Tool 4: get_leads_by_department (Partial 'Global visa') ---")
        result = self.loop.run_until_complete(get_leads_by_department("Global visa"))
        self.assertTrue(result.get("success"))
        self.assertGreater(result.get("total"), 0)
        print(f"[*] Partial search 'Global visa' found {result['total']} leads.")

    def test_09_get_leads_by_department_nonexistent(self):
        print("\n--- Testing Tool 4: get_leads_by_department (Nonexistent Department) ---")
        result = self.loop.run_until_complete(get_leads_by_department("NonexistentDept999"))
        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("total"), 0)
        self.assertEqual(result.get("leads"), [])
        print("[*] Nonexistent department cleanly returns total=0.")

    # -------------------------------------------------------------------------
    # 5. get_leads_by_counselor
    # -------------------------------------------------------------------------
    def test_10_get_leads_by_counselor(self):
        print("\n--- Testing Tool 5: get_leads_by_counselor ---")
        result = self.loop.run_until_complete(get_leads_by_counselor("Administrator"))
        self.assertTrue(result.get("success"), f"Expected success=True, got: {result}")
        print(f"[*] Leads for counselor 'Administrator': Total={result['total']}")
        self.assertIsInstance(result.get("leads"), list)

    def test_11_get_leads_by_counselor_nonexistent(self):
        print("\n--- Testing Tool 5: get_leads_by_counselor (Nonexistent Counselor) ---")
        result = self.loop.run_until_complete(get_leads_by_counselor("nonexistent_user_xyz@test.com"))
        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("total"), 0)
        self.assertEqual(result.get("leads"), [])
        print("[*] Nonexistent counselor cleanly returns total=0.")

    # -------------------------------------------------------------------------
    # 6. get_lead_sources
    # -------------------------------------------------------------------------
    def test_12_get_lead_sources(self):
        print("\n--- Testing Tool 6: get_lead_sources ---")
        result = self.loop.run_until_complete(get_lead_sources("2026-09-01", "2026-09-06"))
        self.assertTrue(result.get("success"), f"Expected success=True, got: {result}")
        self.assertIn("sources", result)
        print(f"[*] Lead sources breakdown: {result['sources']}")
        self.assertIn("Meta Instant Form", result["sources"])

    # -------------------------------------------------------------------------
    # 7. get_unassigned_leads
    # -------------------------------------------------------------------------
    def test_13_get_unassigned_leads(self):
        print("\n--- Testing Tool 7: get_unassigned_leads ---")
        result = self.loop.run_until_complete(get_unassigned_leads("2026-09-06", "2026-09-06"))
        self.assertTrue(result.get("success"), f"Expected success=True, got: {result}")
        self.assertIn("unassigned_leads", result)
        print(f"[*] Unassigned leads today: Total={result['total']}")
        self.assertGreaterEqual(result["total"], 1)

    # -------------------------------------------------------------------------
    # 8. Security & Boundary Assurances
    # -------------------------------------------------------------------------
    def test_14_unauthorized_rejection(self):
        print("\n--- Testing Security: Unauthorized Access Rejection ---")
        unauth_client = FrappeClient(api_key="invalid_key", api_secret="invalid_secret")
        try:
            self.loop.run_until_complete(unauth_client.get_leads_by_date("2026-09-06"))
            self.fail("Should raise FrappeAuthError")
        except FrappeAuthError as exc:
            self.assertIn("authentication failed", str(exc).lower())
            # Ensure no credentials in error message
            self.assertNotIn("invalid_key", str(exc))
            self.assertNotIn("invalid_secret", str(exc))
            print("[*] Unauthorized request rejected securely without exposing credentials.")

    def test_15_no_credentials_leaked_in_responses(self):
        print("\n--- Testing Security: No Credentials Leakage ---")
        result = self.loop.run_until_complete(get_lead_report("2026-09-06", "2026-09-06"))
        result_str = str(result)
        self.assertNotIn(config.frappe_api_key, result_str)
        self.assertNotIn(config.frappe_api_secret, result_str)
        if config.mcp_auth_token:
            self.assertNotIn(config.mcp_auth_token, result_str)
        print("[*] Verified: Zero credentials or private tokens exposed in responses.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
