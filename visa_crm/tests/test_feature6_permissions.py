# Copyright (c) 2026, Shahbaz and contributors
# For license information, please see license.txt

import unittest
from unittest.mock import MagicMock, patch
import frappe
from visa_crm.api.lead_permissions import (
    is_management,
    contact_query,
    contact_permission,
    crm_organization_query,
    crm_organization_permission,
    fcrm_note_query,
    fcrm_note_permission,
    crm_task_query,
    crm_task_permission,
    crm_call_log_query,
    crm_call_log_permission
)


class TestFeature6RoleBasedVisibility(unittest.TestCase):
    def setUp(self):
        if not hasattr(frappe.local, "db") or frappe.local.db is None:
            frappe.local.db = MagicMock()
        if not hasattr(frappe.local, "conf") or frappe.local.conf is None:
            frappe.local.conf = frappe._dict()
        if not hasattr(frappe.local, "flags") or frappe.local.flags is None:
            frappe.local.flags = frappe._dict({"in_test": False})
        self.mock_db = frappe.local.db
        self.mock_db.escape.side_effect = lambda v: f"'{v}'"

    def test_admin_and_management_have_unrestricted_query(self):
        """Admin, Manager, and HR see all records (empty query condition)"""
        for user, roles in [
            ("Administrator", ["Administrator"]),
            ("manager@example.com", ["Sales Manager", "Sales User"]),
            ("hr@example.com", ["HR Manager"]),
            ("crm_mgr@example.com", ["CRM Manager"])
        ]:
            with patch("frappe.get_roles", return_value=roles):
                self.assertTrue(is_management(user))
                self.assertEqual(contact_query(user), "")
                self.assertEqual(crm_organization_query(user), "")
                self.assertEqual(fcrm_note_query(user), "")
                self.assertEqual(crm_task_query(user), "")
                self.assertEqual(crm_call_log_query(user), "")

    def test_admin_and_management_have_full_permission(self):
        """Admin, Manager, and HR can access any employee's record"""
        doc = frappe._dict({"owner": "employee_b@example.com", "name": "DOC-001"})
        for user, roles in [
            ("Administrator", ["Administrator"]),
            ("manager@example.com", ["Sales Manager"]),
            ("hr@example.com", ["HR User"])
        ]:
            with patch("frappe.get_roles", return_value=roles):
                self.assertTrue(contact_permission(doc, user=user))
                self.assertTrue(crm_organization_permission(doc, user=user))
                self.assertTrue(fcrm_note_permission(doc, user=user))
                self.assertTrue(crm_task_permission(doc, user=user))
                self.assertTrue(crm_call_log_permission(doc, user=user))

    def test_normal_employee_query_conditions(self):
        """Normal employees see only their own records in list queries"""
        emp_a = "employee_a@example.com"
        with patch("frappe.get_roles", return_value=["Sales User", "Counselor"]):
            self.assertFalse(is_management(emp_a))
            self.assertEqual(contact_query(emp_a), "`tabContact`.`owner` = 'employee_a@example.com'")
            self.assertEqual(crm_organization_query(emp_a), "`tabCRM Organization`.`owner` = 'employee_a@example.com'")
            self.assertEqual(fcrm_note_query(emp_a), "`tabFCRM Note`.`owner` = 'employee_a@example.com'")
            self.assertIn("employee_a@example.com", crm_task_query(emp_a))
            self.assertIn("assigned_to", crm_task_query(emp_a))
            self.assertIn("caller", crm_call_log_query(emp_a))

    def test_normal_employee_cannot_access_other_employee_records(self):
        """Normal employee A is rejected when attempting to access employee B's records"""
        emp_a = "employee_a@example.com"
        doc_b = frappe._dict({
            "owner": "employee_b@example.com",
            "assigned_to": "employee_b@example.com",
            "caller": "employee_b@example.com",
            "receiver": "customer@example.com"
        })

        with patch("frappe.get_roles", return_value=["Sales User"]):
            # Employee A accessing Employee B's records -> Must be False
            self.assertFalse(contact_permission(doc_b, user=emp_a))
            self.assertFalse(crm_organization_permission(doc_b, user=emp_a))
            self.assertFalse(fcrm_note_permission(doc_b, user=emp_a))
            self.assertFalse(crm_task_permission(doc_b, user=emp_a))
            self.assertFalse(crm_call_log_permission(doc_b, user=emp_a))

    def test_normal_employee_can_access_own_records(self):
        """Normal employee A can access their own records"""
        emp_a = "employee_a@example.com"
        doc_a = frappe._dict({
            "owner": emp_a,
            "assigned_to": emp_a,
            "caller": emp_a,
            "receiver": "customer@example.com"
        })

        with patch("frappe.get_roles", return_value=["Sales User"]):
            self.assertTrue(contact_permission(doc_a, user=emp_a))
            self.assertTrue(crm_organization_permission(doc_a, user=emp_a))
            self.assertTrue(fcrm_note_permission(doc_a, user=emp_a))
            self.assertTrue(crm_task_permission(doc_a, user=emp_a))
            self.assertTrue(crm_call_log_permission(doc_a, user=emp_a))
