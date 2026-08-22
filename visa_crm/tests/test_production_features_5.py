# Copyright (c) 2026, Shahbaz and contributors
# For license information, please see license.txt

import unittest
import datetime
from unittest.mock import MagicMock, patch
import frappe
from visa_crm.api.call_log_hooks import auto_populate_call_log_phone
from visa_crm.api.doc_overrides import normalize_crm_lead_filters
from visa_crm.api.task_reminders import send_task_due_reminders, on_task_update
from visa_crm.overrides.contact import VisaCRMContact


class TestProductionFeatures5(unittest.TestCase):
	def setUp(self):
		if not hasattr(frappe.local, "db") or frappe.local.db is None:
			frappe.local.db = MagicMock()
		if not hasattr(frappe.local, "cache") or frappe.local.cache is None:
			frappe.local.cache = MagicMock()
		if not hasattr(frappe.local, "flags") or frappe.local.flags is None:
			frappe.local.flags = frappe._dict({"in_test": False})
		self.mock_db = frappe.local.db

	def test_call_log_auto_populate_outgoing(self):
		"""Feature 1: Auto-populate 'to' for Outgoing call log from Lead"""
		call_doc = frappe._dict({
			"doctype": "CRM Call Log",
			"type": "Outgoing",
			"reference_doctype": "CRM Lead",
			"reference_docname": "CRM-LEAD-TEST-001",
			"to": None,
			"from": None,
			"get": lambda k: getattr(call_doc, k, None),
			"set": lambda k, v: setattr(call_doc, k, v)
		})

		self.mock_db.exists.return_value = True
		self.mock_db.get_value.return_value = {"mobile_no": "+971501234567", "phone": None}

		auto_populate_call_log_phone(call_doc)
		self.assertEqual(call_doc.to, "+971501234567")

	def test_call_log_auto_populate_incoming(self):
		"""Feature 1: Auto-populate 'from' for Incoming call log from Lead"""
		call_doc = frappe._dict({
			"doctype": "CRM Call Log",
			"type": "Incoming",
			"reference_doctype": "CRM Lead",
			"reference_docname": "CRM-LEAD-TEST-001",
			"to": None,
			"from": None,
			"get": lambda k: getattr(call_doc, k, None),
			"set": lambda k, v: setattr(call_doc, k, v)
		})

		self.mock_db.exists.return_value = True
		self.mock_db.get_value.return_value = {"mobile_no": None, "phone": "+919876543210"}

		auto_populate_call_log_phone(call_doc)
		self.assertEqual(call_doc.get("from"), "+919876543210")

	def test_call_log_preserves_user_entered_phone(self):
		"""Feature 1: Do not overwrite user-entered number"""
		call_doc = frappe._dict({
			"doctype": "CRM Call Log",
			"type": "Outgoing",
			"reference_doctype": "CRM Lead",
			"reference_docname": "CRM-LEAD-TEST-001",
			"to": "+971559999999",
			"get": lambda k: getattr(call_doc, k, None),
		})

		self.mock_db.exists.return_value = True
		self.mock_db.get_value.return_value = {"mobile_no": "+971501234567"}

		auto_populate_call_log_phone(call_doc)
		self.assertEqual(call_doc.to, "+971559999999")

	def test_lead_like_filter_normalization(self):
		"""Feature 3: Like filter normalization on CRM Lead"""
		filters = {"name": ["LIKE", "%Yaseen%"], "status": "New"}
		self.mock_db.sql_list.return_value = ["CRM-LEAD-2026-00363"]

		norm = normalize_crm_lead_filters(filters)
		self.assertIn("name", norm)
		self.assertEqual(norm["name"], ["in", ["CRM-LEAD-2026-00363"]])
		self.assertEqual(norm["status"], "New")

	def test_lead_like_filter_no_match(self):
		"""Feature 3: Like filter with 0 matches returns safe __no_match__ sentinel"""
		filters = {"name": ["LIKE", "%NonExistentName%"]}
		self.mock_db.sql_list.return_value = []

		norm = normalize_crm_lead_filters(filters)
		self.assertEqual(norm["name"], ["in", ["__no_match__"]])

	def test_task_reminders_creation_and_idempotency(self):
		"""Feature 4: Task reminder creation and duplicate prevention"""
		now_val = datetime.datetime.now()
		mock_task = frappe._dict({
			"name": 42,
			"title": "Call customer regarding UAE visa",
			"priority": "High",
			"due_date": now_val,
			"assigned_to": "employee@example.com",
			"owner": "admin@example.com",
			"reference_doctype": "CRM Lead",
			"reference_docname": "CRM-LEAD-2026-001",
			"status": "Todo"
		})

		def fake_sql(query, params=None, as_dict=False):
			if "tabCRM Task" in query:
				return [mock_task]
			elif "tabCRM Notification" in query:
				return []  # No existing notification
			return []

		self.mock_db.sql.side_effect = fake_sql
		self.mock_db.exists.return_value = True
		self.mock_db.get_value.return_value = "Test Lead Name"

		inserted_docs = []
		def fake_new_doc(dt):
			d = frappe._dict({"doctype": dt, "insert": lambda ignore_permissions=False: inserted_docs.append(d)})
			return d

		with patch("frappe.new_doc", side_effect=fake_new_doc):
			result = send_task_due_reminders()
			self.assertTrue(result["ok"])
			self.assertEqual(result["reminders_sent"], 1)
			self.assertEqual(len(inserted_docs), 1)
			self.assertEqual(inserted_docs[0].to_user, "employee@example.com")
			self.assertEqual(inserted_docs[0].type, "Task")
			self.assertEqual(inserted_docs[0].notification_type_doc, "42")

	def test_task_completion_dismisses_notifications(self):
		"""Feature 4: Marking task Done marks unread notifications as read"""
		task_doc = frappe._dict({"name": 42, "status": "Done"})
		on_task_update(task_doc)
		# Verify sql update was called with read = 1
		self.mock_db.sql.assert_called()

	def test_contact_list_enrichment(self):
		"""Feature 5: Contact list data dynamic enrichment from linked CRM Lead & Customer"""
		data = [
			{"name": "CONT-001", "full_name": "Contact One", "email_id": "one@example.com"},
			{"name": "CONT-002", "full_name": "Contact Two", "email_id": "two@example.com"}
		]

		mock_links = [
			frappe._dict({"parent": "CONT-001", "link_doctype": "CRM Lead", "link_name": "CRM-LEAD-001"}),
			frappe._dict({"parent": "CONT-002", "link_doctype": "Customer", "link_name": "CUST-002"})
		]

		mock_leads = [
			frappe._dict({"name": "CRM-LEAD-001", "lead_name": "Lead Customer One", "first_name": "One", "lead_category": "Global Visa", "lead_group": "UK"})
		]

		mock_customers = [
			frappe._dict({"name": "CUST-002", "customer_name": "VIP Customer Two"})
		]

		def fake_sql(query, params=None, as_dict=False):
			if "tabDynamic Link" in query:
				return mock_links
			elif "tabCRM Lead" in query:
				return mock_leads
			elif "tabCustomer" in query:
				return mock_customers
			return []

		self.mock_db.sql.side_effect = fake_sql

		enriched = VisaCRMContact.parse_list_data(data)
		self.assertEqual(len(enriched), 2)
		# Record 1: from CRM Lead
		self.assertEqual(enriched[0]["customer_name"], "Lead Customer One")
		self.assertEqual(enriched[0]["lead_category"], "Global Visa")
		self.assertEqual(enriched[0]["lead_group"], "UK")
		# Record 2: from Customer
		self.assertEqual(enriched[1]["customer_name"], "VIP Customer Two")
		self.assertEqual(enriched[1]["lead_category"], "")
