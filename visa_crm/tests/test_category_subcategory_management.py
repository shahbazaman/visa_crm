import unittest
import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api.lead_management import create_category, create_sub_category, bulk_classify, subcategories
from visa_crm.api.lead_classification import apply_manual_classification
from visa_crm.api.pipeline_stage_services import ai_retry_at


class TestCategorySubcategoryManagement(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        for cat in ["Test Category Alpha", "Test Category Beta", "Test Category Gamma"]:
            if not frappe.db.exists("Lead Category", cat):
                frappe.get_doc({
                    "doctype": "Lead Category",
                    "category_name": cat,
                    "is_active": 1,
                    "sort_order": 100
                }).insert(ignore_permissions=True)

    def test_01_create_category_and_subcategory(self):
        cat_name = "Test Category Unique 100"
        if not frappe.db.exists("Lead Category", cat_name):
            res = create_category(cat_name)
            cat_key = res["name"]
        else:
            cat_key = cat_name

        sub_name = f"Sub Gamma {frappe.generate_hash(length=4)}"
        sub_res = create_sub_category(sub_name, cat_key, description="Subcategory 1")
        self.assertEqual(sub_res["sub_category_name"], sub_name)
        real_parent = sub_res["parent_category"]

        with self.assertRaises(frappe.DuplicateEntryError):
            create_sub_category(sub_name, real_parent)

    def test_02_subcategory_under_different_parent_is_allowed(self):
        sub_name = f"Common Sub {frappe.generate_hash(length=4)}"
        s1 = create_sub_category(sub_name, "Test Category Alpha")
        s2 = create_sub_category(sub_name, "Test Category Beta")
        self.assertEqual(s1["sub_category_name"], sub_name)
        self.assertEqual(s2["sub_category_name"], sub_name)

    def test_03_subcategories_api_returns_parent_filtered_nodes(self):
        sub_name = f"Common Sub {frappe.generate_hash(length=4)}"
        create_sub_category(sub_name, "Test Category Alpha")
        res = subcategories(category="Test Category Alpha")
        self.assertEqual(res["category"], "Test Category Alpha")
        self.assertIn(sub_name.lower(), [s.lower() for s in res["subcategories"]])

    def test_04_single_move_preserves_meta_attribution(self):
        fb_id = f"META-LEAD-TEST-{frappe.generate_hash(length=6)}"
        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "first_name": "MetaLeadTest",
            "lead_name": "Meta Lead Test Case",
            "mobile_no": "+919876543210",
            "facebook_lead_id": fb_id,
            "meta_campaign_name": "Campaign Test Preserved",
            "meta_ad_name": "Ad Test Preserved",
            "meta_adset_name": "Adset Test Preserved",
            "status": "Open",
            "lead_category": "Uncategorized",
        }).insert(ignore_permissions=True)

        res = apply_manual_classification(lead.name, "Test Category Alpha", group="Common Sub", reason="Manual unit test move")
        self.assertEqual(res["lead_category"], "Test Category Alpha")
        self.assertEqual(res["lead_group"].lower(), "common sub")

        reloaded = frappe.get_doc("CRM Lead", lead.name)
        self.assertEqual(reloaded.lead_category, "Test Category Alpha")
        self.assertEqual(reloaded.lead_group.lower(), "common sub")

        # Verify Meta Attribution Preserved
        self.assertEqual(reloaded.facebook_lead_id, fb_id)
        self.assertEqual(reloaded.meta_campaign_name, "Campaign Test Preserved")
        self.assertEqual(reloaded.meta_ad_name, "Ad Test Preserved")
        self.assertEqual(reloaded.meta_adset_name, "Adset Test Preserved")

    def test_05_bulk_move_and_move_back_to_uncategorised(self):
        l1 = frappe.get_doc({"doctype": "CRM Lead", "first_name": "B1", "lead_name": "Bulk Lead Test 1", "status": "Open"}).insert(ignore_permissions=True)
        l2 = frappe.get_doc({"doctype": "CRM Lead", "first_name": "B2", "lead_name": "Bulk Lead Test 2", "status": "Open"}).insert(ignore_permissions=True)

        res_bulk = bulk_classify([l1.name, l2.name], "Test Category Beta", group="Common Sub", reason="Bulk move unit test")
        self.assertTrue(res_bulk["ok"])
        self.assertEqual(res_bulk["moved"], 2)
        self.assertEqual(len(res_bulk["results"]), 2)

        self.assertEqual(frappe.db.get_value("CRM Lead", l1.name, "lead_category"), "Test Category Beta")
        self.assertEqual(frappe.db.get_value("CRM Lead", l2.name, "lead_category"), "Test Category Beta")

        # Move back to Uncategorized
        res_uncat = bulk_classify([l1.name], "Uncategorized", group="Unspecified", reason="Move back to uncategorized")
        self.assertTrue(res_uncat["ok"])
        self.assertEqual(frappe.db.get_value("CRM Lead", l1.name, "lead_category"), "Uncategorized")
        # Document still exists and is intact
        self.assertTrue(frappe.db.exists("CRM Lead", l1.name))

    def test_06_gemini_429_quota_backoff_delays(self):
        from frappe.utils import now_datetime, time_diff_in_seconds

        # Test daily quota exhaustion 429 error
        err_daily_quota = 'Gemini API HTTP 429: {"error": {"code": 429, "message": "Quota exceeded for GenerateRequestsPerDayPerProjectPerModel-FreeTier limit: 20 model: gemini-2.5-flash"}}'
        retry_at = ai_retry_at(1, at=now_datetime(), error_str=err_daily_quota)
        diff = time_diff_in_seconds(retry_at, now_datetime())
        # Must enforce minimum 3600 seconds (1 hour) backoff for daily quota
        self.assertGreaterEqual(diff, 3590)

        # Test 429 with parsed retryDelay
        err_retry_delay = 'HTTP 429 RESOURCE_EXHAUSTED Please retry in 45s'
        retry_at_delay = ai_retry_at(1, at=now_datetime(), error_str=err_retry_delay)
        diff_delay = time_diff_in_seconds(retry_at_delay, now_datetime())
        self.assertGreaterEqual(diff_delay, 40)

        # Test permanent 401 Auth error returns None (no retry)
        err_auth = 'Gemini API HTTP 401: Invalid API Key'
        self.assertIsNone(ai_retry_at(1, error_str=err_auth))

    def test_07_production_lead_invariants(self):
        if frappe.db.exists("Lead Intake Queue", "LIQ-2026-00007"):
            queue = frappe.get_doc("Lead Intake Queue", "LIQ-2026-00007")
            self.assertTrue(bool(queue.source_lead_id))
            self.assertTrue(bool(queue.matched_lead))
            self.assertTrue(bool(queue.matched_customer))

            if frappe.db.exists("CRM Lead", "CRM-LEAD-2026-00129"):
                lead = frappe.get_doc("CRM Lead", "CRM-LEAD-2026-00129")
                self.assertTrue(bool(lead.lead_name))
                self.assertTrue(bool(lead.meta_campaign_name))

            if frappe.db.exists("Customer", "Meta Lead 1272720881498434"):
                customer = frappe.get_doc("Customer", "Meta Lead 1272720881498434")
                self.assertTrue(bool(customer.customer_name))

    def test_08_sidepanel_and_table_campaign_name(self):
        from frappe.utils import cint
        meta = frappe.get_meta("CRM Lead")
        df = meta.get_field("meta_campaign_name")
        self.assertIsNotNone(df)
        self.assertEqual(df.label, "Campaign Name")
        self.assertEqual(cint(df.read_only), 1)

        from crm.fcrm.doctype.crm_fields_layout.crm_fields_layout import get_sidepanel_sections
        sections = get_sidepanel_sections("CRM Lead")
        details = next((s for s in sections if s.get("name") in ("details_section", "Details") or s.get("label") == "Details"), None)
        self.assertIsNotNone(details)
        cols = details.get("columns") or []
        fields = [f.get("fieldname") if isinstance(f, dict) else str(f) for c in cols for f in (c.get("fields") or [])]
        self.assertIn("meta_campaign_name", fields)

        from visa_crm.api.lead_tree import get_lead_tree_nodes
        nodes = get_lead_tree_nodes(parent_level="Leads", category="All", subcategory="All", filters='{"page":1, "page_length":20}')
        leads_list = nodes.get("data") or []
        if frappe.db.exists("CRM Lead", "CRM-LEAD-2026-00129"):
            prod_lead = next((l for l in leads_list if l.get("name") == "CRM-LEAD-2026-00129"), None)
            if prod_lead:
                self.assertEqual(prod_lead.get("meta_campaign_name"), "Thailand rizwann")
