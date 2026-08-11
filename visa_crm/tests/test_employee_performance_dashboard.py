import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api.meta_utils import has_doctype
from visa_crm.api.dashboard import (
    employee_interaction_detail,
    employee_interactions,
    employee_list_for_dashboard,
    employee_performance_dashboard,
)


class TestEmployeePerformanceDashboard(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        emp_list = frappe.get_all("Employee", filters={"status": "Active"}, pluck="name")
        if emp_list:
            self.employee_id = emp_list[0]
        else:
            self.employee_id = "HR-EMP-00001"
            if not frappe.db.exists("Employee", self.employee_id):
                emp = frappe.get_doc({
                    "doctype": "Employee",
                    "name": self.employee_id,
                    "first_name": "Test",
                    "last_name": "Counselor",
                    "employee_name": "Test Counselor",
                    "gender": "Male",
                    "date_of_birth": "1990-01-01",
                    "date_of_joining": "2020-01-01",
                    "status": "Active"
                })
                emp.insert(ignore_permissions=True)

    def test_admin_and_management_access_allowed(self):
        frappe.set_user("Administrator")
        res = employee_list_for_dashboard()
        self.assertTrue(isinstance(res, list))

    def test_page_exists_and_no_conflicting_workspace(self):
        page_exists = frappe.db.exists("Page", "employee-dashboard")
        self.assertTrue(page_exists, "Page 'employee-dashboard' must exist in DocType Page")

        ws_count = frappe.db.count("Workspace", filters={"label": "Employee Dashboard"})
        ws_count += frappe.db.count("Workspace", filters={"name": ["in", ["Employee Dashboard", "employee-dashboard"]]})
        self.assertEqual(ws_count, 0, "Conflicting Workspace 'Employee Dashboard' must not exist in DB")

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_unauthorized_counselor_access_rejected(self):
        try:
            frappe.set_user("Guest")
            with self.assertRaises(frappe.PermissionError):
                employee_list_for_dashboard()

            with self.assertRaises(frappe.PermissionError):
                employee_performance_dashboard(employee=self.employee_id)

            with self.assertRaises(frappe.PermissionError):
                employee_interactions(employee=self.employee_id)

            with self.assertRaises(frappe.PermissionError):
                employee_interaction_detail("CE-TEST")
        finally:
            frappe.set_user("Administrator")

    def test_employee_selector_returns_active_employees(self):
        frappe.set_user("Administrator")
        employees = employee_list_for_dashboard()
        emp_names = [e["name"] for e in employees]
        self.assertIn(self.employee_id, emp_names)

    def test_single_employee_data_isolation(self):
        frappe.set_user("Administrator")
        dash = employee_performance_dashboard(employee=self.employee_id, preset="this_month")
        self.assertEqual(dash["employee"]["name"], self.employee_id)
        self.assertIn("summary", dash)
        self.assertIn("ai_metrics", dash)

    def test_ai_insufficient_data_and_score_basis(self):
        frappe.set_user("Administrator")
        emp = frappe.get_doc({
            "doctype": "Employee",
            "first_name": "No AI Employee",
            "gender": "Male",
            "date_of_birth": "1990-01-01",
            "date_of_joining": "2020-01-01",
            "status": "Active"
        })
        emp.insert(ignore_permissions=True)

        dash = employee_performance_dashboard(employee=emp.name, preset="this_month")
        self.assertTrue(dash["ai_metrics"]["insufficient_data"])
        self.assertIsNone(dash["ai_metrics"]["overall_score"])

    def test_exact_interaction_counting_and_no_double_counting(self):
        frappe.set_user("Administrator")
        c1 = frappe.get_doc({
            "doctype": "Communication Event",
            "employee": self.employee_id,
            "source": "Phone",
            "event_type": "Call",
            "direction": "Inbound",
            "status": "Closed",
            "ai_score": 90.0,
            "event_datetime": frappe.utils.now_datetime()
        }).insert(ignore_permissions=True)

        c2 = frappe.get_doc({
            "doctype": "Communication Event",
            "employee": self.employee_id,
            "source": "WhatsApp",
            "event_type": "Chat",
            "direction": "Outbound",
            "status": "Closed",
            "ai_score": 80.0,
            "event_datetime": frappe.utils.now_datetime()
        }).insert(ignore_permissions=True)

        inter = employee_interactions(employee=self.employee_id, preset="this_month")
        names = [i["name"] for i in inter["interactions"]]
        self.assertIn(c1.name, names)
        self.assertIn(c2.name, names)

    def test_interaction_drill_down_links(self):
        frappe.set_user("Administrator")
        c = frappe.get_doc({
            "doctype": "Communication Event",
            "employee": self.employee_id,
            "source": "Phone",
            "event_type": "Call",
            "status": "Closed",
            "event_datetime": frappe.utils.now_datetime()
        }).insert(ignore_permissions=True)

        detail = employee_interaction_detail(c.name)
        self.assertIn("communication_event", detail)
        self.assertEqual(detail["communication_event"]["name"], c.name)

    def test_failed_ai_evaluations_do_not_become_zero_score(self):
        frappe.set_user("Administrator")
        c_failed = frappe.get_doc({
            "doctype": "Communication Event",
            "employee": self.employee_id,
            "source": "Meta Form",
            "event_type": "Lead",
            "status": "Pending",
            "ai_score": None,
            "event_datetime": frappe.utils.now_datetime()
        }).insert(ignore_permissions=True)

        if has_doctype("Lead Intake AI Job"):
            liq = frappe.get_all("Lead Intake Queue", limit=1, pluck="name")
            liq_id = liq[0] if liq else frappe.get_doc({"doctype": "Lead Intake Queue"}).insert(ignore_permissions=True).name

            frappe.get_doc({
                "doctype": "Lead Intake AI Job",
                "idempotency_key": f"test-failed-{c_failed.name}",
                "queue": liq_id,
                "communication_event": c_failed.name,
                "state": "FAILED",
                "last_error": "Gemini text generation method is not configured"
            }).insert(ignore_permissions=True)

        inter = employee_interactions(employee=self.employee_id, preset="this_month", ai_status="Failed")
        failed_names = [i["name"] for i in inter["interactions"]]
        self.assertIn(c_failed.name, failed_names)
        matching = next(i for i in inter["interactions"] if i["name"] == c_failed.name)
        self.assertEqual(matching["ai_status"], "Failed")
        self.assertIsNone(matching["ai_score"])
