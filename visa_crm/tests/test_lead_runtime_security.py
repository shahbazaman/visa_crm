import frappe
from frappe.permissions import _pop_debug_log
from frappe.tests.utils import FrappeTestCase

from visa_crm.api import lead_management
from visa_crm.api import lead_permissions


class TestLeadRuntimeSecurity(FrappeTestCase):
    def setUp(self):
        suffix = frappe.generate_hash(length=8).lower()
        self.user_one = f"mail-owner-{suffix}@example.com"
        self.user_two = f"mail-peer-{suffix}@example.com"
        self._make_user(self.user_one)
        self._make_user(self.user_two)

        account = frappe.get_doc({
            "doctype": "Email Account",
            "email_account_name": f"Runtime Mail {suffix}",
            "email_id": self.user_one,
            "service": "GMail",
            "auth_method": "Basic",
            "enable_incoming": 0,
            "enable_outgoing": 0,
        })
        account.insert(ignore_permissions=True)
        frappe.db.set_value(
            "Email Account",
            account.name,
            {"owner": self.user_one, "connected_user": self.user_one},
            update_modified=False,
        )
        self.account = account.name

        self.shared_lead = self._make_lead("Uncategorized", suffix, "shared")
        self.restricted_lead = self._make_lead("Global Visa", suffix, "restricted")

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.delete("CRM Lead", {"name": ["in", [self.shared_lead, self.restricted_lead]]})
        frappe.db.delete("Email Account", {"name": self.account})
        for user in (self.user_one, self.user_two):
            frappe.db.delete("Has Role", {"parent": user})
            frappe.db.delete("User", {"name": user})
        frappe.clear_cache()

    def test_other_employee_cannot_list_or_open_private_mailbox(self):
        frappe.set_user(self.user_two)
        names = frappe.get_list("Email Account", pluck="name")
        self.assertNotIn(self.account, names)
        account = frappe.get_doc("Email Account", self.account)
        self.assertFalse(account.has_permission("read", user=self.user_two))

        frappe.set_user(self.user_one)
        self.assertIn(self.account, frappe.get_list("Email Account", pluck="name"))
        self.assertTrue(frappe.get_doc("Email Account", self.account).has_permission("read", user=self.user_one))

    def test_operational_user_gets_shared_category_but_not_unmapped_category(self):
        frappe.set_user(self.user_two)
        dashboard = lead_management.dashboard()
        category_names = {row["name"] for row in dashboard["categories"]}
        self.assertIn("Uncategorized", category_names)
        shared = frappe.get_doc("CRM Lead", self.shared_lead)
        self.assertEqual(shared.lead_category, "Uncategorized")
        self.assertTrue(lead_permissions.crm_lead_permission(shared, "read", self.user_two))
        permitted = shared.has_permission("read", user=self.user_two, debug=True)
        self.assertTrue(permitted, "\n".join(_pop_debug_log()))
        self.assertIn(self.shared_lead, {row.name for row in lead_management.leads("Uncategorized")["rows"]})
        self.assertFalse(frappe.get_doc("CRM Lead", self.restricted_lead).has_permission("read", user=self.user_two))
        with self.assertRaises(frappe.PermissionError):
            lead_management.leads("Global Visa")

    def _make_user(self, email):
        user = frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": "Runtime",
            "last_name": "Security",
            "enabled": 1,
            "send_welcome_email": 0,
            "user_type": "System User",
        })
        user.insert(ignore_permissions=True)
        user.add_roles("Sales User", "Inbox User")

    def _make_lead(self, category, suffix, label):
        lead = frappe.new_doc("CRM Lead")
        lead.first_name = f"Runtime {label} {suffix}"
        if lead.meta.has_field("lead_name"):
            lead.lead_name = lead.first_name
        lead.lead_category = category
        lead.lead_group = "Unspecified"
        lead.classification_source = "Automatic"
        lead.classification_status = "Classified" if category != "Uncategorized" else "Needs Review"
        lead.insert(ignore_permissions=True)
        return lead.name
