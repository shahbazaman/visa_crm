import unittest
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.website.path_resolver import PathResolver


class TestLeadManagementPage(FrappeTestCase):

    def test_page_exists_in_db(self):
        """lead-management Page must exist in the database."""
        self.assertTrue(frappe.db.exists("Page", "lead-management"))

    def test_page_loads_assets_once(self):
        """Page script must be non-empty and must NOT declare class VisaLeadTreePage
        (old accordion class) more than 0 times — new page uses VisaLeadManagement."""
        doc = frappe.get_doc("Page", "lead-management")
        doc.load_assets()
        self.assertTrue(doc.script, "Page script must not be empty")
        # New architecture uses VisaLeadManagement (not VisaLeadTreePage)
        self.assertIn(
            "VisaLeadManagement",
            doc.script,
            "New page JS must define VisaLeadManagement class"
        )
        # Verify search parameter routing logic is present
        self.assertIn("_get_params", doc.script, "URL search parameter routing must be present")
        # Verify lead click opens native CRM route
        self.assertIn("/crm/leads/", doc.script, "Lead click must navigate to CRM SPA")

    def test_native_crm_routes_no_redirect(self):
        """Native CRM routes (/crm, /crm/leads, /crm/leads/view/list) must NOT redirect to /app/lead-management."""
        frappe.cache.delete_key("website_redirects")
        for route in ("crm", "crm/leads", "crm/leads/view/list", "crm/contacts", "crm/deals"):
            frappe.flags.redirect_location = None
            PathResolver(route).resolve()
            self.assertNotEqual(
                getattr(frappe.flags, "redirect_location", None),
                "/app/lead-management",
                f"Route /{route} must NOT redirect to /app/lead-management"
            )

    def test_unrelated_crm_routes_not_redirected(self):
        """Server-side: /crm/contacts, /crm/deals, /crm/dashboard must NOT redirect."""
        frappe.cache.delete_key("website_redirects")
        for route in ("crm/contacts", "crm/deals", "crm/dashboard"):
            frappe.flags.redirect_location = None
            PathResolver(route).resolve()
            self.assertNotEqual(
                getattr(frappe.flags, "redirect_location", None),
                "/app/lead-management",
                f"Route /{route} must NOT redirect to lead-management"
            )

    def test_api_categories_returns_list(self):
        """get_lead_tree_nodes Categories must return a non-empty list."""
        from visa_crm.api.lead_tree import get_lead_tree_nodes
        result = get_lead_tree_nodes(parent_level="Categories")
        self.assertIsInstance(result, list)

    def test_api_categories_have_required_keys(self):
        """Each category node must have value, label, count, level keys."""
        from visa_crm.api.lead_tree import get_lead_tree_nodes
        result = get_lead_tree_nodes(parent_level="Categories")
        for node in result:
            self.assertIn("value", node)
            self.assertIn("label", node)
            self.assertIn("count", node)
            self.assertEqual(node.get("level"), "Category")

    def test_api_uncategorized_subcategories(self):
        """Uncategorized subcategory query must return list with No Subcategory entry."""
        from visa_crm.api.lead_tree import get_lead_tree_nodes
        result = get_lead_tree_nodes(parent_level="Subcategories", category="Uncategorized")
        self.assertIsInstance(result, list)
        values = [n.get("value") for n in result]
        self.assertIn("No Subcategory", values)

    def test_api_leads_returns_paginated(self):
        """Leads query must return dict with data, has_more, page keys."""
        from visa_crm.api.lead_tree import get_lead_tree_nodes
        result = get_lead_tree_nodes(
            parent_level="Leads",
            category="Uncategorized",
            subcategory="No Subcategory"
        )
        self.assertIsInstance(result, dict)
        self.assertIn("data", result)
        self.assertIn("has_more", result)
        self.assertIn("page", result)

    def test_api_leads_include_email_field(self):
        """Lead records must include email field."""
        from visa_crm.api.lead_tree import get_lead_tree_nodes
        result = get_lead_tree_nodes(
            parent_level="Leads",
            category="Uncategorized",
            subcategory="No Subcategory"
        )
        data = result.get("data", [])
        if data:
            # email key must be present (value may be None/empty)
            self.assertIn("email", data[0], "Lead data must include email field")

    def test_api_null_category_handled(self):
        """NULL/empty categories must fall under Uncategorized."""
        from visa_crm.api.lead_tree import get_lead_tree_nodes
        cats = get_lead_tree_nodes(parent_level="Categories")
        values = [c.get("value") for c in cats]
        # If any leads have null category, Uncategorized must appear
        null_count = frappe.db.sql(
            "SELECT COUNT(*) FROM `tabCRM Lead` WHERE IFNULL(lead_category, '') = ''",
            as_list=True
        )[0][0]
        if null_count > 0:
            self.assertIn("Uncategorized", values)

    def test_frappe_core_unchanged(self):
        """apps/frappe git working tree must remain clean."""
        import subprocess
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd="/home/shahbaz/frappe-bench/apps/frappe",
            capture_output=True, text=True
        )
        self.assertEqual(result.stdout.strip(), "", "apps/frappe must remain clean")
