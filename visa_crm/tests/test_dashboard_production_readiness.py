import os
import frappe
from frappe.tests.utils import FrappeTestCase

class TestDashboardProductionReadiness(FrappeTestCase):
    def test_employee_dashboard_page_record_and_roles(self):
        self.assertTrue(frappe.db.exists("Page", "employee-dashboard"))
        page_doc = frappe.get_doc("Page", "employee-dashboard")
        roles = {r.role for r in page_doc.roles}
        expected = {"System Manager", "Sales Manager", "General Manager", "Managing Director", "MD", "CRM Manager"}
        self.assertTrue(expected.issubset(roles), f"Missing management roles on Page employee-dashboard: {expected - roles}")

    def test_no_conflicting_employee_workspaces(self):
        ws_count = frappe.db.count("Workspace", filters={"name": ["like", "%employee%"]})
        ws_count += frappe.db.count("Workspace", filters={"label": ["like", "%employee%"]})
        self.assertEqual(ws_count, 0, "No Workspace matching '%employee%' should exist in database")

    def test_page_js_hook_points_to_public_js(self):
        import visa_crm.hooks as hooks
        page_js = getattr(hooks, "page_js", {})
        self.assertEqual(page_js.get("employee-dashboard"), "public/js/employee_dashboard.js")

    def test_public_js_file_exists_and_contains_build_marker(self):
        full_path = frappe.get_app_path("visa_crm", "public/js/employee_dashboard.js")
        self.assertTrue(os.path.exists(full_path), f"File missing at {full_path}")
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("DASHBOARD_BUILD_ID", content)
        self.assertIn('frappe.pages["employee-dashboard"].on_page_load', content)

    def test_dashboard_rpc_methods_callable(self):
        for method in (
            "visa_crm.api.dashboard.employee_list_for_dashboard",
            "visa_crm.api.dashboard.employee_performance_dashboard",
            "visa_crm.api.dashboard.employee_interactions",
            "visa_crm.api.dashboard.employee_interaction_detail"
        ):
            fn = frappe.get_attr(method)
            self.assertTrue(callable(fn), f"RPC method {method} is not callable")
