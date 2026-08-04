from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from visa_crm.api.lead_classification import classify_payload, classify_queue, default_rules, derive_group, normalize_text


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
