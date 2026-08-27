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
		self.mock_db.reset_mock()
		self.mock_db.side_effect = None

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

	def test_lead_tree_category_subcategory_filters(self):
		"""Feature 3: Map URL/Tree query params 'category' and 'subcategory' to Lead fields"""
		filters = {"category": "Global Visa", "subcategory": "Global"}
		norm = normalize_crm_lead_filters(filters)
		self.assertEqual(norm.get("lead_category"), "Global Visa")
		self.assertEqual(norm.get("lead_group"), "Global")
		self.assertNotIn("category", norm)
		self.assertNotIn("subcategory", norm)

	def test_task_reminders_creation_and_idempotency(self):
		"""Feature 4: Task reminder creation and duplicate prevention"""
		now_val = datetime.datetime.now()
		mock_task = frappe._dict({
			"name": "TASK-001",
			"title": "Call client back",
			"priority": "High",
			"due_date": now_val + datetime.timedelta(hours=2),
			"assigned_to": "employee@example.com",
			"owner": "admin@example.com",
			"reference_doctype": "CRM Lead",
			"reference_docname": "CRM-LEAD-001"
		})

		self.mock_db.sql.side_effect = [
			[mock_task],  # open tasks
			[],           # existing notifications (none)
		]

		created_docs = []
		def mock_new_doc(dt):
			doc = frappe._dict({"doctype": dt})
			doc.insert = lambda ignore_permissions=False: created_docs.append(doc)
			return doc

		with patch("frappe.new_doc", side_effect=mock_new_doc):
			with patch("frappe.publish_realtime"):
				res = send_task_due_reminders()

		self.assertEqual(res.get("reminders_sent"), 1)
		self.assertEqual(len(created_docs), 1)
		self.assertEqual(created_docs[0].to_user, "employee@example.com")
		self.assertEqual(created_docs[0].notification_type_doc, "TASK-001")

	def test_task_completion_dismisses_reminder(self):
		"""Feature 4: Completing a task marks reminder as read"""
		task_doc = frappe._dict({
			"doctype": "CRM Task",
			"name": "TASK-001",
			"status": "Done"
		})

		self.mock_db.sql.side_effect = None
		self.mock_db.sql.return_value = 1

		on_task_update(task_doc)
		self.mock_db.sql.assert_called_once()
		sql_arg = self.mock_db.sql.call_args[0][0]
		self.assertIn("UPDATE `tabCRM Notification`", sql_arg)
		self.assertIn("SET `read` = 1", sql_arg)

	def test_contact_list_data_structure(self):
		"""Feature 5: Contacts list default columns contain Customer Name, Category, Subcategory"""
		list_meta = VisaCRMContact.default_list_data()
		col_keys = [c["key"] for c in list_meta["columns"]]
		self.assertIn("customer_name", col_keys)
		self.assertIn("lead_category", col_keys)
		self.assertIn("lead_group", col_keys)
		# Rows queried from DB should only contain physical columns
		self.assertNotIn("customer_name", list_meta["rows"])
		self.assertNotIn("lead_category", list_meta["rows"])
		self.assertNotIn("lead_group", list_meta["rows"])

	def test_contact_parse_list_data_enrichment(self):
		"""Feature 5: parse_list_data enriches customer_name from linked CRM Lead"""
		sample_data = [
			{"name": "CONT-001", "full_name": "Contact 1"},
			{"name": "CONT-002", "full_name": "Contact 2"}
		]

		self.mock_db.sql.side_effect = [
			[
				frappe._dict({"parent": "CONT-001", "link_doctype": "CRM Lead", "link_name": "LEAD-001"}),
			],
			[
				frappe._dict({"name": "LEAD-001", "lead_name": "John Doe Corp", "first_name": "John", "last_name": "Doe", "lead_category": "Immigration", "lead_group": "Canada"}),
			]
		]

		enriched = VisaCRMContact.parse_list_data(sample_data)
		self.assertEqual(enriched[0]["customer_name"], "John Doe Corp")
		self.assertEqual(enriched[0]["lead_category"], "Immigration")
		self.assertEqual(enriched[0]["lead_group"], "Canada")
		self.assertEqual(enriched[1]["customer_name"], "Contact 2")


if __name__ == "__main__":
	unittest.main()
