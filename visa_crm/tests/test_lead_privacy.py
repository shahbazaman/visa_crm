from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from visa_crm.api import lead_permissions


class TestLeadPrivacyQueries(FrappeTestCase):
    def test_email_account_query_is_owner_scoped(self):
        with patch.object(lead_permissions, "is_management", return_value=False), patch.object(lead_permissions, "is_operational", return_value=True), patch.object(lead_permissions, "_user_email_accounts", return_value=["Employee Mail"]):
            condition = lead_permissions.email_account_query("employee@example.com")
        self.assertIn("owner", condition)
        self.assertIn("connected_user", condition)
        self.assertIn("Employee Mail", condition)

    def test_user_without_category_mapping_gets_no_lead_rows(self):
        with patch.object(lead_permissions, "is_management", return_value=False), patch.object(lead_permissions, "is_operational", return_value=True), patch.object(lead_permissions, "accessible_categories", return_value=[]):
            self.assertEqual(lead_permissions.crm_lead_query("employee@example.com"), "1=0")

    def test_category_condition_is_database_enforced(self):
        with patch.object(lead_permissions, "is_management", return_value=False), patch.object(lead_permissions, "is_operational", return_value=True), patch.object(lead_permissions, "accessible_categories", return_value=["Global Visa", "Uncategorized"]):
            condition = lead_permissions.crm_lead_query("employee@example.com")
        self.assertIn("tabCRM Lead", condition)
        self.assertIn("Global Visa", condition)
        self.assertIn("Uncategorized", condition)
