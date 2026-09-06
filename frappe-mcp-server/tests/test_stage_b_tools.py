"""
Test Suite: Stage B Operational Tools (Phase 3).
Validates Follow-ups, Tasks, and Visa Application MCP tools against live production.
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
    get_followups,
    get_tasks,
    get_visa_applications,
)


class TestStageBOperationalTools(unittest.TestCase):
    """Test suite for Stage B operational capabilities."""

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    # -------------------------------------------------------------------------
    # 1. get_followups
    # -------------------------------------------------------------------------
    def test_01_get_followups_live(self):
        print("\n--- Testing Tool 8: get_followups (Live Unfiltered) ---")
        result = self.loop.run_until_complete(get_followups())
        self.assertTrue(result.get("success"), f"Expected success=True, got: {result}")
        self.assertIn("total", result)
        self.assertIn("followups", result)
        self.assertIsInstance(result["followups"], list)
        print(f"[*] get_followups live total: {result['total']}")
        if result["followups"]:
            sample = result["followups"][0]
            print(f"[*] Sample Follow-up: ID={sample.get('name')}, Status={sample.get('status')}, Due={sample.get('due_date')}")
            self.assertIn("name", sample)
            self.assertIn("description", sample)
            self.assertIn("status", sample)

    def test_02_get_followups_date_range(self):
        print("\n--- Testing Tool 8: get_followups (Date Range 2026-08-01 to 2026-09-06) ---")
        result = self.loop.run_until_complete(get_followups("2026-08-01", "2026-09-06"))
        self.assertTrue(result.get("success"))
        print(f"[*] Follow-ups in date range: Total={result['total']}")

    def test_03_get_followups_invalid_date(self):
        print("\n--- Testing Tool 8: get_followups (Invalid Date Format) ---")
        result = self.loop.run_until_complete(get_followups("invalid-date", "2026-09-06"))
        self.assertFalse(result.get("success"))
        self.assertIn("error", result)
        print(f"[*] Correctly rejected bad date: {result['error']}")

    # -------------------------------------------------------------------------
    # 2. get_tasks
    # -------------------------------------------------------------------------
    def test_04_get_tasks_live(self):
        print("\n--- Testing Tool 9: get_tasks (Live Tasks) ---")
        result = self.loop.run_until_complete(get_tasks())
        self.assertTrue(result.get("success"), f"Expected success=True, got: {result}")
        self.assertIn("total", result)
        self.assertIn("tasks", result)
        self.assertIsInstance(result["tasks"], list)
        print(f"[*] get_tasks live total: {result['total']}")
        if result["tasks"]:
            sample = result["tasks"][0]
            print(f"[*] Sample Task: Name={sample.get('task_name')}, Assigned={sample.get('assigned_employee')}, Due={sample.get('due_date')}")
            self.assertIn("task_name", sample)
            self.assertIn("subject", sample)
            self.assertIn("status", sample)

    def test_05_get_tasks_by_employee(self):
        print("\n--- Testing Tool 9: get_tasks (Filter by Employee 'Administrator') ---")
        result = self.loop.run_until_complete(get_tasks(assigned_employee="Administrator"))
        self.assertTrue(result.get("success"))
        print(f"[*] Tasks assigned to Administrator: Total={result['total']}")

    def test_06_get_tasks_invalid_range(self):
        print("\n--- Testing Tool 9: get_tasks (Inverted Date Range) ---")
        result = self.loop.run_until_complete(get_tasks("2026-09-10", "2026-09-01"))
        self.assertFalse(result.get("success"))
        self.assertIn("error", result)
        print(f"[*] Correctly rejected inverted date range: {result['error']}")

    # -------------------------------------------------------------------------
    # 3. get_visa_applications
    # -------------------------------------------------------------------------
    def test_07_get_visa_applications_live(self):
        print("\n--- Testing Tool 10: get_visa_applications (Live Visas) ---")
        result = self.loop.run_until_complete(get_visa_applications())
        self.assertTrue(result.get("success"), f"Expected success=True, got: {result}")
        self.assertIn("total", result)
        self.assertIn("visa_applications", result)
        self.assertIsInstance(result["visa_applications"], list)
        print(f"[*] get_visa_applications live total: {result['total']}")
        self.assertGreater(result["total"], 0, "Expected at least 1 visa application in production")
        sample = result["visa_applications"][0]
        print(f"[*] Sample Visa: Name={sample.get('name')}, Applicant={sample.get('applicant_name')}, Status={sample.get('status')}")
        self.assertIn("name", sample)
        self.assertIn("status", sample)

    def test_08_get_visa_applications_by_status(self):
        print("\n--- Testing Tool 10: get_visa_applications (Status 'Draft') ---")
        result = self.loop.run_until_complete(get_visa_applications(status="Draft"))
        self.assertTrue(result.get("success"))
        print(f"[*] Visa applications with status 'Draft': Total={result['total']}")

    def test_09_get_visa_applications_invalid_date(self):
        print("\n--- Testing Tool 10: get_visa_applications (Invalid Date) ---")
        result = self.loop.run_until_complete(get_visa_applications("bad-date"))
        self.assertFalse(result.get("success"))
        self.assertIn("error", result)
        print(f"[*] Correctly rejected bad date: {result['error']}")

    # -------------------------------------------------------------------------
    # 4. Security
    # -------------------------------------------------------------------------
    def test_10_no_secrets_in_operational_results(self):
        print("\n--- Testing Security: Zero Credential Leakage in Stage B ---")
        result = self.loop.run_until_complete(get_visa_applications())
        res_str = str(result)
        self.assertNotIn(config.frappe_api_key, res_str)
        self.assertNotIn(config.frappe_api_secret, res_str)
        if config.mcp_auth_token:
            self.assertNotIn(config.mcp_auth_token, res_str)
        print("[*] Stage B results contain zero credentials or tokens.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
