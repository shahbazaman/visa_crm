import unittest
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.website.path_resolver import PathResolver

class TestLeadManagementPage(FrappeTestCase):
    def test_page_exists_and_loads_assets(self):
        self.assertTrue(frappe.db.exists("Page", "lead-management"))
        doc = frappe.get_doc("Page", "lead-management")
        doc.load_assets()
        self.assertTrue(doc.script)
        # Verify class VisaLeadTreePage is defined only once to prevent SyntaxError
        occurrences = doc.script.count("class VisaLeadTreePage")
        self.assertEqual(occurrences, 1, f"class VisaLeadTreePage appeared {occurrences} times in doc.script")

    def test_redirect_hook_registration(self):
        redirects = frappe.get_hooks("website_redirects")
        target = next((r for r in redirects if r.get("source") == "/crm/leads/view/list"), None)
        self.assertIsNotNone(target)
        self.assertEqual(target.get("target"), "/app/lead-management")

    def test_targeted_redirect_resolution(self):
        frappe.cache.delete_key("website_redirects")
        res_endpoint, _ = PathResolver("crm/leads/view/list").resolve()
        self.assertEqual(res_endpoint, "/app/lead-management")
        self.assertEqual(getattr(frappe.flags, "redirect_location", None), "/app/lead-management")

    def test_unrelated_crm_routes_not_redirected(self):
        frappe.cache.delete_key("website_redirects")
        for route in ("crm", "crm/contacts", "crm/deals"):
            frappe.flags.redirect_location = None
            res_endpoint, _ = PathResolver(route).resolve()
            self.assertNotEqual(getattr(frappe.flags, "redirect_location", None), "/app/lead-management")
