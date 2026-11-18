from unittest.mock import patch
import frappe
from frappe.tests.utils import FrappeTestCase

from visa_crm.api.lead_classification import (
    classify_payload,
    classify_queue,
    default_rules,
    derive_group,
    normalize_text,
    ensure_lead_subcategory,
    backfill_meta_leads_classification
)


class TestLeadClassification(FrappeTestCase):
    def classify(self, payload, source=None, rules=None):
        with patch("visa_crm.api.lead_classification.category_department", return_value=None):
            return classify_payload(payload, source, rules=default_rules() if rules is None else rules)

    def test_meta_visa_suffix_is_case_and_whitespace_safe(self):
        result = self.classify({"source_lead_id": "META-1", "campaign_name": "  UK   VISA  ", "visa_type": "Family Visit"})
        self.assertEqual(result["lead_category"], "Global Visa")
        self.assertEqual(result["lead_group"], "Family Visit")

    def test_meta_package_suffix_creates_normalized_group(self):
        result = self.classify({"source_lead_id": "META-2", "campaign_name": "  bALI_package "})
        self.assertEqual(result["lead_category"], "Holidays")
        self.assertEqual(result["lead_group"], "Bali")

    def test_whatsapp_source_has_priority(self):
        result = self.classify({"campaign_name": "UK Visa"}, "WhatsApp")
        self.assertEqual(result["lead_category"], "Reservation")

    def test_unmatched_meta_is_never_hidden(self):
        result = self.classify({"source_lead_id": "META-3", "campaign_name": "General Awareness"})
        self.assertEqual(result["lead_category"], "Uncategorized")
        self.assertEqual(result["classification_status"], "Needs Review")
        self.assertEqual(result["classification_reason"], "No classification rule matched")

    def test_google_ads_is_configurable_not_implicitly_active(self):
        inactive_result = self.classify({}, "Google Ads")
        self.assertEqual(inactive_result["lead_category"], "Uncategorized")
        rules = [{"name": "future-google", "source_channel": "Google Ads", "match_field": "Source", "match_type": "Equals", "match_value": "Google Ads", "category": "Google Ads"}]
        active_result = self.classify({}, "Google Ads", rules=rules)
        self.assertEqual(active_result["lead_category"], "Google Ads")

    def test_normalization_does_not_split_equivalent_groups(self):
        self.assertEqual(normalize_text("  BALI_package "), normalize_text("bali package"))
        self.assertEqual(derive_group("Holidays", {"campaign_name": "BALI PACKAGE"}), "Bali")

    def test_manual_classification_is_not_overwritten_on_retry(self):
        queue = frappe._dict({
            "name": "LIQ-MANUAL",
            "classification_source": "Manual",
            "lead_category": "Holidays",
            "lead_group": "Bali",
            "matched_lead": "CRM-LEAD-MANUAL",
        })
        with patch("visa_crm.api.lead_classification.frappe.get_doc", return_value=queue), patch(
            "visa_crm.api.lead_classification.sync_lead_classification"
        ) as sync:
            result = classify_queue(queue.name)
        self.assertTrue(result["reused"])
        self.assertEqual(result["classification"]["lead_category"], "Holidays")
        sync.assert_called_once()

    # --- MANDATORY MATRIX TESTS (SECTION 10) ---

    def test_matrix_holidays_campaign_suffix(self):
        cases = [
            ("Azerbaijan Campaign", "Holidays", "Azerbaijan"),
            ("Vietnam Campaign", "Holidays", "Vietnam"),
            ("Azerbaijan Leads", "Holidays", "Azerbaijan"),
            ("Vietnam Leads", "Holidays", "Vietnam"),
            ("Azerbaijan Campign", "Holidays", "Azerbaijan"),
            ("Europe Holiday Campaign", "Holidays", "Europe"),
        ]
        for cname, expected_cat, expected_grp in cases:
            res = self.classify({"source_lead_id": "M1", "campaign_name": cname})
            self.assertEqual(res["lead_category"], expected_cat, f"Failed category for {cname}")
            self.assertEqual(res["lead_group"], expected_grp, f"Failed group for {cname}")

    def test_matrix_global_visa_suffix(self):
        cases = [
            ("Azerbaijan Visa", "Global Visa", "Azerbaijan"),
            ("Vietnam Visa", "Global Visa", "Vietnam"),
            ("USA Visa", "Global Visa", "USA"),
            ("Schengen Visa", "Global Visa", "Schengen"),
        ]
        for cname, expected_cat, expected_grp in cases:
            res = self.classify({"source_lead_id": "M2", "campaign_name": cname})
            self.assertEqual(res["lead_category"], expected_cat, f"Failed category for {cname}")
            self.assertEqual(res["lead_group"], expected_grp, f"Failed group for {cname}")

    def test_case_and_separator_tolerance(self):
        cases = [
            ("AZERBAIJAN_CAMPAIGN", "Holidays", "Azerbaijan"),
            ("Vietnam-Leads", "Holidays", "Vietnam"),
            ("Europe Holiday CAMPAIGN", "Holidays", "Europe"),
            ("  azerbaijan   campign  ", "Holidays", "Azerbaijan"),
            ("veitnam campaign", "Holidays", "Vietnam"),
            ("VIETNAM_VISA", "Global Visa", "Vietnam"),
        ]
        for cname, expected_cat, expected_grp in cases:
            res = self.classify({"source_lead_id": "M3", "campaign_name": cname})
            self.assertEqual(res["lead_category"], expected_cat, f"Failed category for {cname}")
            self.assertEqual(res["lead_group"], expected_grp, f"Failed group for {cname}")

    def test_rule_priority_visa_over_campaign_substring(self):
        # A campaign ending in 'visa' must route to Global Visa
        res = self.classify({"source_lead_id": "M4", "campaign_name": "Europe Visa"})
        self.assertEqual(res["lead_category"], "Global Visa")
        self.assertEqual(res["lead_group"], "Europe")

        # A campaign ending in 'campaign' must route to Holidays
        res = self.classify({"source_lead_id": "M5", "campaign_name": "Europe Campaign"})
        self.assertEqual(res["lead_category"], "Holidays")
        self.assertEqual(res["lead_group"], "Europe")

    def test_subcategory_parent_isolation_and_reuse(self):
        # Test that subcategory lookup respects parent_category and does not mix Holidays and Global Visa
        if frappe.db.exists("DocType", "Lead Subcategory"):
            # Ensure parents exist
            for p in ["Holidays", "Global Visa"]:
                if not frappe.db.exists("Lead Category", p):
                    frappe.get_doc({"doctype": "Lead Category", "category_name": p, "is_active": 1}).insert(ignore_permissions=True)

            sub_h = ensure_lead_subcategory("Holidays", "Azerbaijan")
            sub_v = ensure_lead_subcategory("Global Visa", "Azerbaijan")

            # They must be distinct records linked to their respective parents
            doc_h = frappe.get_doc("Lead Subcategory", sub_h)
            doc_v = frappe.get_doc("Lead Subcategory", sub_v)
            self.assertEqual(doc_h.parent_category, "Holidays")
            self.assertEqual(doc_v.parent_category, "Global Visa")
            self.assertNotEqual(doc_h.name, doc_v.name)

            # Re-running ensure_lead_subcategory must reuse exact same record
            sub_h_again = ensure_lead_subcategory("Holidays", "azerbaijan")
            self.assertEqual(sub_h_again, sub_h)

    def test_unknown_destination_and_generic_fallback(self):
        # Campaign with no recognizable destination but suffix 'campaign'
        res = self.classify({"source_lead_id": "M6", "campaign_name": "Special Offer Campaign"})
        self.assertEqual(res["lead_category"], "Holidays")
        self.assertEqual(res["lead_group"], "Unspecified")

        # Completely unmatched campaign
        res_unmatched = self.classify({"source_lead_id": "M7", "campaign_name": "Random Brand Promo"})
        self.assertEqual(res_unmatched["lead_category"], "Uncategorized")
        self.assertEqual(res_unmatched["classification_status"], "Needs Review")
        # Test lead with dummy question answers should not create dummy subcategories
        res_dummy = self.classify({
            "source_lead_id": "M8",
            "campaign_name": "",
            "custom_destination": "<test lead: dummy data for which destination are you interested in?>"
        })
        self.assertEqual(res_dummy["lead_category"], "Uncategorized")
        self.assertEqual(res_dummy["lead_group"], "Unspecified")

        # Campaign with recruitment typo 'hirng'
        res_hiring = self.classify({
            "source_lead_id": "M9",
            "campaign_name": "visa hirng for kochi"
        })
        self.assertEqual(res_hiring["lead_category"], "Global Visa")
        self.assertEqual(res_hiring["lead_group"], "Sales Hiring")

