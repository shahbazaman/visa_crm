# Copyright (c) 2026, Shahbaz and contributors
# For license information, please see license.txt

import unittest
from unittest.mock import MagicMock, patch
import frappe

from visa_crm.api.whatsapp_integration import (
	normalize_phone_number,
	get_phone_search_variants,
	find_matching_crm_lead,
	find_matching_customer,
	whatsapp_access_guard,
	validate_access,
	on_whatsapp_message_validate,
	on_whatsapp_message_after_insert,
	ALLOWED_WHATSAPP_ROLES,
)


class TestWhatsAppIntegration(unittest.TestCase):
	def setUp(self):
		frappe.local.db = MagicMock()
		frappe.local.session = frappe._dict({"user": "Administrator"})
		frappe.local.cache = MagicMock()
		frappe.local.flags = frappe._dict({"in_test": False})
		frappe.local.message_log = []
		frappe.local.response = frappe._dict()
		frappe.local.debug_log = []
		self.mock_db = frappe.local.db

	def test_phone_normalization_uae(self):
		self.assertEqual(normalize_phone_number("0501234567"), "+971501234567")
		self.assertEqual(normalize_phone_number("050 123 4567"), "+971501234567")
		self.assertEqual(normalize_phone_number("+971 50 123 4567"), "+971501234567")
		self.assertEqual(normalize_phone_number("971501234567"), "+971501234567")
		self.assertEqual(normalize_phone_number("00971501234567"), "+971501234567")

	def test_phone_normalization_india(self):
		self.assertEqual(normalize_phone_number("09837909369"), "+919837909369")
		self.assertEqual(normalize_phone_number("9837909369"), "+919837909369")
		self.assertEqual(normalize_phone_number("+91 98379 09369"), "+919837909369")
		self.assertEqual(normalize_phone_number("919837909369"), "+919837909369")
		self.assertEqual(normalize_phone_number("00919837909369"), "+919837909369")

	def test_phone_search_variants(self):
		variants = get_phone_search_variants("+971501234567")
		self.assertIn("+971501234567", variants)
		self.assertIn("971501234567", variants)
		self.assertIn("0501234567", variants)
		self.assertIn("501234567", variants)

	def test_find_matching_crm_lead_with_mock(self):
		self.mock_db.sql.side_effect = None
		self.mock_db.sql.return_value = ["CRM-LEAD-2026-00001"]
		lead = find_matching_crm_lead("+971501234567")
		self.assertEqual(lead, "CRM-LEAD-2026-00001")

	def test_find_matching_customer_with_mock(self):
		self.mock_db.sql.side_effect = None
		self.mock_db.sql.return_value = ["CUST-2026-00001"]
		cust = find_matching_customer("+971501234567")
		self.assertEqual(cust, "CUST-2026-00001")

	def test_whatsapp_access_guard_admin(self):
		frappe.local.session.user = "Administrator"
		# Should not throw
		whatsapp_access_guard()

	def test_whatsapp_access_guard_counselor(self):
		frappe.local.session.user = "counselor@example.com"
		with patch.object(frappe, "get_roles", return_value=["Counselor", "All"]):
			whatsapp_access_guard()

	def test_whatsapp_access_guard_unauthorized(self):
		frappe.local.session.user = "guest@example.com"
		with patch.object(frappe, "get_roles", return_value=["Guest", "Customer"]):
			with patch("visa_crm.api.whatsapp_integration.is_management", return_value=False):
				with patch("visa_crm.api.whatsapp_integration.is_operational", return_value=False):
					with self.assertRaises(frappe.PermissionError):
						whatsapp_access_guard()

	def test_on_whatsapp_message_validate_links_lead(self):
		mock_doc = MagicMock()
		mock_doc.direction = "Incoming"
		mock_doc.message_id = "wamid.HBgL..."
		mock_doc.reference_doctype = None
		mock_doc.reference_docname = None
		mock_doc.get.side_effect = lambda k: "+971501234567" if k == "from" else None
		mock_doc.is_new.return_value = True

		self.mock_db.exists.return_value = False

		with patch("visa_crm.api.whatsapp_integration.find_matching_crm_lead", return_value="CRM-LEAD-2026-00100"):
			on_whatsapp_message_validate(mock_doc)
			self.assertEqual(mock_doc.reference_doctype, "CRM Lead")
			self.assertEqual(mock_doc.reference_docname, "CRM-LEAD-2026-00100")

	def test_on_whatsapp_message_after_insert_emits_realtime(self):
		mock_doc = MagicMock()
		mock_doc.direction = "Incoming"
		mock_doc.reference_doctype = "CRM Lead"
		mock_doc.reference_docname = "CRM-LEAD-2026-00100"
		mock_doc.name = "WAM-00001"
		mock_doc.get.side_effect = lambda k: "wamid.123" if k == "message_id" else "Hello Counselor"
		mock_doc.owner = "Administrator"

		with patch.object(frappe, "publish_realtime") as mock_realtime:
			self.mock_db.get_value.return_value = {"lead_owner": "counselor@test.com", "lead_name": "Test Lead"}
			self.mock_db.exists.return_value = True
			with patch.object(frappe, "new_doc") as mock_new_doc:
				mock_notif = MagicMock()
				mock_new_doc.return_value = mock_notif
				on_whatsapp_message_after_insert(mock_doc)

				mock_realtime.assert_called_once_with(
					"whatsapp_message",
					{
						"reference_doctype": "CRM Lead",
						"reference_name": "CRM-LEAD-2026-00100",
						"message_id": "wamid.123",
						"name": "WAM-00001",
					},
				)
				mock_notif.insert.assert_called_once()
				self.assertEqual(mock_notif.to_user, "counselor@test.com")

	def test_is_whatsapp_enabled_with_active_account(self):
		from visa_crm.api.whatsapp_integration import is_whatsapp_enabled
		self.mock_db.exists.return_value = True
		self.mock_db.get_single_value.side_effect = lambda dt, field: "WABA-001" if field == "default_account" else None
		self.mock_db.get_value.return_value = "Active"
		self.assertTrue(is_whatsapp_enabled())

	def test_is_whatsapp_enabled_with_no_account(self):
		from visa_crm.api.whatsapp_integration import is_whatsapp_enabled
		self.mock_db.exists.return_value = True
		self.mock_db.get_single_value.return_value = None
		with patch("frappe.get_all", return_value=[]):
			self.assertFalse(is_whatsapp_enabled())

	def test_is_whatsapp_installed(self):
		from visa_crm.api.whatsapp_integration import is_whatsapp_installed
		self.mock_db.exists.return_value = True
		self.assertTrue(is_whatsapp_installed())
