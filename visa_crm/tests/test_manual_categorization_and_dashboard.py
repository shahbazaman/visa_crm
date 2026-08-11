import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api.lead_classification import apply_manual_classification
from visa_crm.api.lead_management import bulk_classify, leads, subcategories
from visa_crm.api.dashboard import employee_performance_dashboard


class TestManualCategorizationAndDashboard(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        if not frappe.db.exists("Lead Category", "Schengen Visa"):
            doc = frappe.get_doc({
                "doctype": "Lead Category",
                "category_name": "Schengen Visa",
                "category_key": "schengen_visa",
                "is_active": 1,
                "operational_status": "Active"
            })
            doc.insert(ignore_permissions=True)

        if not frappe.db.exists("Lead Category", "Holidays"):
            doc = frappe.get_doc({
                "doctype": "Lead Category",
                "category_name": "Holidays",
                "category_key": "holidays",
                "is_active": 1,
                "operational_status": "Active"
            })
            doc.insert(ignore_permissions=True)

    def test_manual_classification_updates_lead_and_creates_history(self):
        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "lead_name": "Test Manual Lead",
            "mobile_no": "+919999888777",
            "status": "Open",
            "lead_category": "Uncategorized",
            "classification_source": "Automatic"
        })
        lead.insert(ignore_permissions=True)

        result = apply_manual_classification(lead.name, "Schengen Visa", group="France Tourist", reason="Customer requested France visa")
        self.assertEqual(result["lead_category"], "Schengen Visa")
        self.assertEqual(result["lead_group"], "France Tourist")
        self.assertEqual(result["classification_source"], "Manual")

        updated_lead = frappe.get_doc("CRM Lead", lead.name)
        self.assertEqual(updated_lead.lead_category, "Schengen Visa")
        self.assertEqual(updated_lead.lead_group, "France Tourist")
        self.assertEqual(updated_lead.classification_source, "Manual")

        history = frappe.get_all("Lead Classification History", filters={"lead": lead.name}, fields=["old_category", "new_category", "old_group", "new_group", "classification_source"])
        self.assertTrue(len(history) > 0)
        self.assertEqual(history[0].new_category, "Schengen Visa")
        self.assertEqual(history[0].classification_source, "Manual")

    def test_invalid_category_raises_error(self):
        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "lead_name": "Test Invalid Category Lead",
            "status": "Open"
        })
        lead.insert(ignore_permissions=True)

        with self.assertRaises(frappe.ValidationError):
            apply_manual_classification(lead.name, "NonExistentCategory999")

    def test_bulk_classify_atomic_execution(self):
        l1 = frappe.get_doc({"doctype": "CRM Lead", "lead_name": "Bulk Lead 1", "status": "Open"}).insert(ignore_permissions=True)
        l2 = frappe.get_doc({"doctype": "CRM Lead", "lead_name": "Bulk Lead 2", "status": "Open"}).insert(ignore_permissions=True)

        res = bulk_classify([l1.name, l2.name], "Holidays", group="Europe Package", reason="Bulk manual assignment test")
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["succeeded"]), 2)
        self.assertEqual(len(res["failed"]), 0)

        self.assertEqual(frappe.db.get_value("CRM Lead", l1.name, "lead_category"), "Holidays")
        self.assertEqual(frappe.db.get_value("CRM Lead", l2.name, "lead_category"), "Holidays")

    def test_subcategories_api_returns_valid_groups(self):
        res = subcategories()
        self.assertIn("categories", res)
        self.assertIn("subcategories", res)

    def test_lead_list_classification_filter(self):
        l_cat = frappe.get_doc({"doctype": "CRM Lead", "lead_name": "Categorized Lead", "status": "Open", "lead_category": "Holidays"}).insert(ignore_permissions=True)
        l_uncat = frappe.get_doc({"doctype": "CRM Lead", "lead_name": "Uncategorized Lead", "status": "Open", "lead_category": "Uncategorized"}).insert(ignore_permissions=True)

        res_cat = leads(category="All", classification_filter="Categorized")
        cat_names = [row["name"] for row in res_cat.get("rows", [])]
        self.assertIn(l_cat.name, cat_names)

        res_uncat = leads(category="All", classification_filter="Uncategorized")
        uncat_names = [row["name"] for row in res_uncat.get("rows", [])]
        self.assertIn(l_uncat.name, uncat_names)

    def test_employee_performance_dashboard(self):
        dash = employee_performance_dashboard()
        self.assertIn("top_cards", dash)
        self.assertIn("communication_performance", dash)
        self.assertIn("ai_performance", dash)
        self.assertIn("pipeline_health", dash)
        self.assertIn("total_leads", dash["top_cards"])
