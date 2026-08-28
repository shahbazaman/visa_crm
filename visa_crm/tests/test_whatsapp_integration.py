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
	is_whatsapp_enabled,
	is_whatsapp_installed,
	get_whatsapp_messages,
	create_whatsapp_message,
	get_or_create_whatsapp_profile,
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
		whatsapp_access_guard()

	def test_whatsapp_access_guard_counselor(self):
		frappe.local.session.user = "counselor@example.com"
		with patch("frappe.get_roles", return_value=["Counselor", "Desk User"]):
			whatsapp_access_guard()

	def test_whatsapp_access_guard_unauthorized(self):
		frappe.local.session.user = "visitor@example.com"
		with patch("frappe.get_roles", return_value=["Guest"]):
			with self.assertRaises(frappe.PermissionError):
				whatsapp_access_guard()

	def test_on_whatsapp_message_validate_links_lead(self):
		doc = frappe._dict({
			"direction": "Incoming",
			"from": "+971501234567",
			"to": "Primary WhatsApp",
			"reference_doctype": None,
			"reference_docname": None,
			"is_new": lambda: True,
			"message_id": "wamid.test12345",
			"get": lambda k, default=None: "+971501234567" if k == "from" else default,
		})
		self.mock_db.exists.return_value = False
		with patch("visa_crm.api.whatsapp_integration.find_matching_crm_lead", return_value="CRM-LEAD-2026-00001"):
			on_whatsapp_message_validate(doc)
			self.assertEqual(doc.reference_doctype, "CRM Lead")
			self.assertEqual(doc.reference_docname, "CRM-LEAD-2026-00001")

	def test_on_whatsapp_message_after_insert_emits_realtime(self):
		doc = frappe._dict({
			"name": "MSG-0001",
			"direction": "Incoming",
			"reference_doctype": "CRM Lead",
			"reference_docname": "CRM-LEAD-2026-00001",
			"message_id": "wamid.test12345",
			"get": lambda k, default=None: "Incoming" if k == "direction" else default,
			"owner": "Administrator",
		})
		self.mock_db.get_value.return_value = frappe._dict({
			"lead_owner": "counselor@example.com",
			"assigned_employee": None,
			"lead_name": "Test Customer",
			"mobile_no": "+971501234567",
		})
		self.mock_db.exists.return_value = True
		with patch("frappe.publish_realtime") as mock_pub, 		     patch("frappe.new_doc") as mock_new:
			notif_mock = MagicMock()
			mock_new.return_value = notif_mock
			on_whatsapp_message_after_insert(doc)
			mock_pub.assert_called_once()
			mock_new.assert_called_once_with("CRM Notification")
			notif_mock.insert.assert_called_once()

	def test_is_whatsapp_enabled_with_active_account(self):
		self.mock_db.exists.return_value = True
		self.mock_db.get_single_value.side_effect = lambda dt, field: "WABA-001" if field == "default_account" else None
		self.mock_db.get_value.return_value = "Active"
		self.assertTrue(is_whatsapp_enabled())

	def test_is_whatsapp_enabled_with_no_account(self):
		self.mock_db.exists.return_value = True
		self.mock_db.get_single_value.return_value = None
		with patch("frappe.get_all", return_value=[]):
			self.assertFalse(is_whatsapp_enabled())

	def test_is_whatsapp_installed(self):
		self.mock_db.exists.return_value = True
		self.assertTrue(is_whatsapp_installed())

	def test_get_or_create_whatsapp_profile(self):
		self.mock_db.exists.return_value = True
		self.mock_db.get_value.return_value = "WP-001"
		res = get_or_create_whatsapp_profile("+971501234567", "Primary WhatsApp")
		self.assertEqual(res, "WP-001")

	def test_get_whatsapp_messages(self):
		self.mock_db.exists.return_value = True
		mock_doc = MagicMock()
		mock_doc.get.side_effect = lambda k, default=None: "Test Lead" if k in ("lead_name", "customer_name") else default
		mock_doc.has_permission.return_value = True

		mock_msg = frappe._dict({
			"name": "MSG-001",
			"direction": "Incoming",
			"from": "+971501234567",
			"to": "Primary WhatsApp",
			"message": "Hello from lead",
			"status": "Read",
			"creation": "2026-08-28 10:00:00",
			"attach": "",
			"message_id": "wamid.123",
			"context_message_id": "",
			"reply_to_message": "",
			"reference_doctype": "CRM Lead",
			"reference_docname": "CRM-LEAD-001",
			"is_template": 0,
			"whatsapp_template": None,
		})

		with patch("frappe.get_doc", return_value=mock_doc), 		     patch("frappe.get_all", return_value=[mock_msg]):
			msgs = get_whatsapp_messages("CRM Lead", "CRM-LEAD-001")
			self.assertEqual(len(msgs), 1)
			self.assertEqual(msgs[0]["type"], "Incoming")
			self.assertEqual(msgs[0]["message"], "Hello from lead")
			self.assertEqual(msgs[0]["from_name"], "Test Lead")

	def test_create_whatsapp_message(self):
		self.mock_db.exists.return_value = True
		self.mock_db.get_single_value.return_value = "Primary WhatsApp"
		self.mock_db.get_value.return_value = None

		mock_doc = MagicMock()
		mock_doc.name = "CRM-LEAD-001"
		mock_doc.get.side_effect = lambda k, default=None: "Test Lead" if k in ("lead_name", "customer_name") else default
		mock_doc.has_permission.return_value = True

		mock_msg_doc = MagicMock()
		mock_msg_doc.name = "NEW-MSG-001"

		with patch("frappe.get_doc", return_value=mock_doc), 		     patch("visa_crm.api.whatsapp_integration.get_or_create_whatsapp_profile", return_value="WP-001"), 		     patch("frappe.new_doc", return_value=mock_msg_doc):
			name = create_whatsapp_message("CRM Lead", "CRM-LEAD-001", "Hello", "+971501234567")
			self.assertEqual(name, "NEW-MSG-001")
			mock_msg_doc.insert.assert_called_once()


if __name__ == "__main__":
	unittest.main()
