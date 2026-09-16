# Copyright (c) 2026, Shahbaz and contributors
# For license information, please see license.txt

import unittest
from unittest.mock import MagicMock, patch
import frappe
from visa_crm.overrides.crm_page_renderer import CRMPageRenderer


class TestCRMPageRenderer(unittest.TestCase):
	def setUp(self):
		if not getattr(frappe.local, "site", None):
			frappe.init(site="local.test", sites_path="/home/shahbaz/frappe-bench/sites")
			frappe.connect()

	def test_can_render_crm_routes(self):
		for path in ["crm", "/crm", "crm/", "crm/whatsapp", "/crm/whatsapp", "crm/leads/CRM-LEAD-001"]:
			renderer = CRMPageRenderer(path)
			self.assertTrue(renderer.can_render(), f"Expected can_render to be True for {path}")

	def test_can_not_render_non_crm_routes(self):
		for path in ["app", "desk", "api/method/version", "login"]:
			renderer = CRMPageRenderer(path)
			self.assertFalse(renderer.can_render(), f"Expected can_render to be False for {path}")

	@patch("crm.api.check_app_permission", return_value=True)
	@patch("crm.www.crm.get_context")
	def test_render_generates_response(self, mock_get_context, mock_check_perm):
		mock_get_context.return_value = frappe._dict({
			"boot": {"csrf_token": "test-token", "site_name": "local.test"}
		})
		renderer = CRMPageRenderer("crm")
		with patch.object(renderer, "build_response", return_value="OK_RESPONSE"):
			resp = renderer.render()
			self.assertEqual(resp, "OK_RESPONSE")


if __name__ == "__main__":
	unittest.main()
