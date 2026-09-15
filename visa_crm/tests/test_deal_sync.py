import unittest
from unittest.mock import MagicMock, patch
import frappe

# Mock frappe.local
if not hasattr(frappe.local, "db") or not frappe.local.db:
    frappe.local.db = MagicMock()
if not hasattr(frappe.local, "site"):
    frappe.local.site = "test.local"

from visa_crm.api.deal_sync import (
    parse_numeric_budget,
    ensure_contact_for_deal,
    map_lead_to_deal,
    sync_lead_to_deal_validate,
    audit_and_backfill_deals,
)
from visa_crm.api.doc_overrides import enrich_deal_list_data
from visa_crm.overrides.deal import VisaCRMDeal


class TestDealSync(unittest.TestCase):
    def setUp(self):
        frappe.local.db = MagicMock()
        frappe.local.db.exists.return_value = True

    def test_parse_numeric_budget(self):
        self.assertEqual(parse_numeric_budget("₹70,000"), 70000.0)
        self.assertEqual(parse_numeric_budget("50,000 INR"), 50000.0)
        self.assertEqual(parse_numeric_budget("1.5 Lakhs"), 150000.0)
        self.assertEqual(parse_numeric_budget("2.25 Lac"), 225000.0)
        self.assertEqual(parse_numeric_budget(85000), 85000.0)
        self.assertEqual(parse_numeric_budget(None), 0.0)
        self.assertEqual(parse_numeric_budget(""), 0.0)
        self.assertEqual(parse_numeric_budget("N/A"), 0.0)

    def test_visacrmdeal_default_list_data(self):
        data = VisaCRMDeal.default_list_data()
        self.assertIn("columns", data)
        self.assertIn("rows", data)
        col_keys = [c["key"] for c in data["columns"]]
        self.assertIn("lead_name", col_keys)
        self.assertIn("mobile_no", col_keys)
        self.assertIn("email", col_keys)
        self.assertIn("custom_meta_campaign_name", col_keys)
        self.assertIn("custom_meta_adset_name", col_keys)
        self.assertIn("custom_lead_category", col_keys)
        self.assertIn("custom_destination", col_keys)
        self.assertIn("custom_responsible_department", col_keys)
        self.assertIn("status", col_keys)
        self.assertIn("expected_deal_value", col_keys)
        self.assertEqual(len(data["columns"]), 14)

    def test_map_lead_to_deal_fields(self):
        # Mock deal doc
        deal_doc = MagicMock()
        deal_doc.lead = None
        deal_doc.lead_name = None
        deal_doc.first_name = None
        deal_doc.last_name = None
        deal_doc.email = None
        deal_doc.mobile_no = None
        deal_doc.phone = None
        deal_doc.job_title = None
        deal_doc.organization = None
        deal_doc.organization_name = None
        deal_doc.source = None
        deal_doc.deal_owner = None
        deal_doc.expected_deal_value = 0
        deal_doc.deal_value = 0
        deal_doc.annual_revenue = 0
        deal_doc.custom_meta_campaign_name = None
        deal_doc.custom_meta_campaign_id = None
        deal_doc.custom_meta_adset_name = None
        deal_doc.custom_meta_adset_id = None
        deal_doc.custom_meta_ad_name = None
        deal_doc.custom_meta_ad_id = None
        deal_doc.custom_facebook_form_id = None
        deal_doc.custom_facebook_lead_id = None
        deal_doc.custom_lead_category = None
        deal_doc.custom_lead_group = None
        deal_doc.custom_responsible_department = None
        deal_doc.custom_destination = None
        deal_doc.custom_visa_type = None
        deal_doc.custom_travel_month = None
        deal_doc.custom_budget = None
        deal_doc.custom_assigned_counselor = None
        deal_doc.custom_customer = None
        deal_doc.contacts = []
        deal_doc.contact = None

        # Mock lead doc
        lead_doc = MagicMock()
        lead_doc.name = "CRM-LEAD-2026-00099"
        lead_doc.lead_name = "Jane Doe"
        lead_doc.first_name = "Jane"
        lead_doc.last_name = "Doe"
        lead_doc.email = "jane.doe@example.com"
        lead_doc.mobile_no = "+919876543210"
        lead_doc.phone = "+919876543210"
        lead_doc.job_title = "Architect"
        lead_doc.organization = "Design Studio"
        lead_doc.organization_name = "Design Studio"
        lead_doc.source = "Meta Ads"
        lead_doc.lead_owner = "admin@example.com"
        lead_doc.custom_budget = "₹1,20,000"
        lead_doc.meta_campaign_name = "Europe_Autumn_2026"
        lead_doc.meta_campaign_id = "CAMP_12345"
        lead_doc.meta_adset_name = "Kozhikode_Professionals"
        lead_doc.meta_adset_id = "ADSET_6789"
        lead_doc.meta_ad_name = "Ad_Single_Image_1"
        lead_doc.meta_ad_id = "AD_999"
        lead_doc.facebook_form_id = "FORM_111"
        lead_doc.facebook_lead_id = "FB_LEAD_222"
        lead_doc.lead_category = "Tourist Visa"
        lead_doc.lead_group = "Schengen"
        lead_doc.responsible_department = "Europe Operations"
        lead_doc.custom_destination = "France"
        lead_doc.custom_visa_type = "Short Stay"
        lead_doc.custom_travel_month = "October 2026"
        lead_doc.assigned_counselor = "EMP-00001"
        lead_doc.customer = "CUST-0005"

        with patch("frappe.get_meta") as mock_meta, \
             patch("visa_crm.api.deal_sync.ensure_contact_for_deal"):
            mock_deal_meta = MagicMock()
            mock_deal_meta.has_field.return_value = True
            mock_meta.return_value = mock_deal_meta

            updated = map_lead_to_deal(deal_doc, lead_doc, overwrite_existing=False)

            self.assertIn("lead", updated)
            self.assertIn("lead_name", updated)
            self.assertIn("email", updated)
            self.assertIn("mobile_no", updated)
            self.assertIn("custom_meta_campaign_name", updated)
            self.assertIn("custom_destination", updated)
            self.assertEqual(deal_doc.lead_name, "Jane Doe")
            self.assertEqual(deal_doc.email, "jane.doe@example.com")
            self.assertEqual(deal_doc.mobile_no, "+919876543210")
            self.assertEqual(deal_doc.custom_meta_campaign_name, "Europe_Autumn_2026")
            self.assertEqual(deal_doc.custom_destination, "France")
            self.assertEqual(deal_doc.expected_deal_value, 120000.0)

    def test_sync_lead_to_deal_validate_restores_cleared_fields(self):
        deal_doc = MagicMock()
        deal_doc.name = "DEAL-0001"
        deal_doc.lead = "CRM-LEAD-0001"
        deal_doc.email = ""
        deal_doc.mobile_no = ""
        deal_doc.phone = ""
        deal_doc.lead_name = ""

        mock_lead = MagicMock()
        mock_lead.email = "restored@example.com"
        mock_lead.mobile_no = "+919999988888"
        mock_lead.phone = "+919999988888"
        mock_lead.lead_name = "Restored Lead"

        with patch("frappe.get_cached_doc", return_value=mock_lead), \
             patch("visa_crm.api.deal_sync.ensure_contact_for_deal"):
            sync_lead_to_deal_validate(deal_doc)

            self.assertEqual(deal_doc.email, "restored@example.com")
            self.assertEqual(deal_doc.mobile_no, "+919999988888")
            self.assertEqual(deal_doc.lead_name, "Restored Lead")

    def test_enrich_deal_list_data_batch(self):
        deal_rows = [
            {
                "name": "DEAL-101",
                "lead": "CRM-LEAD-101",
                "lead_name": "",
                "email": "",
                "mobile_no": "",
                "custom_meta_campaign_name": "",
            },
            {
                "name": "DEAL-102",
                "lead": "CRM-LEAD-102",
                "lead_name": "Already Set",
                "email": "existing@example.com",
                "mobile_no": "123456",
                "custom_meta_campaign_name": "Existing Campaign",
            },
        ]

        mock_lead_101 = MagicMock()
        mock_lead_101.name = "CRM-LEAD-101"
        mock_lead_101.lead_name = "Enriched Candidate"
        mock_lead_101.first_name = "Enriched"
        mock_lead_101.last_name = "Candidate"
        mock_lead_101.email = "enriched@example.com"
        mock_lead_101.mobile_no = "+919111122222"
        mock_lead_101.phone = "+919111122222"
        mock_lead_101.meta_campaign_name = "Batch_Campaign"
        mock_lead_101.meta_adset_name = "Adset_1"
        mock_lead_101.lead_category = "Tourist"
        mock_lead_101.responsible_department = "Europe"
        mock_lead_101.custom_destination = "Switzerland"

        with patch("frappe.get_all", return_value=[mock_lead_101]):
            enriched = enrich_deal_list_data(deal_rows)

            self.assertEqual(enriched[0]["lead_name"], "Enriched Candidate")
            self.assertEqual(enriched[0]["email"], "enriched@example.com")
            self.assertEqual(enriched[0]["mobile_no"], "+919111122222")
            self.assertEqual(enriched[0]["custom_meta_campaign_name"], "Batch_Campaign")

            # Preserves existing row
            self.assertEqual(enriched[1]["lead_name"], "Already Set")
            self.assertEqual(enriched[1]["email"], "existing@example.com")


if __name__ == "__main__":
    unittest.main()
