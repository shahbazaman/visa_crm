# Copyright (c) 2026, Shahbaz and contributors
# For license information, please see license.txt

import unittest
from unittest.mock import MagicMock, patch
import frappe
from visa_crm.api.deal_sync import (
    parse_numeric_budget,
    ensure_contact_for_deal,
    map_lead_to_deal,
    sync_lead_to_deal_validate,
    sync_lead_to_deal_before_insert,
    sync_lead_to_linked_deal_after_save,
    audit_and_backfill_deals,
)
from visa_crm.api.doc_overrides import enrich_deal_list_data
from visa_crm.overrides.deal import VisaCRMDeal


class TestDealSyncComprehensive(unittest.TestCase):
    def setUp(self):
        if not getattr(frappe.local, "site", None):
            frappe.init(site="local.test", sites_path="/home/shahbaz/frappe-bench/sites")
            frappe.connect()

    def test_01_lead_to_deal_customer_name_mapping(self):
        """1. Lead -> Deal customer name mapping."""
        deal_doc = MagicMock()
        deal_doc.lead_name = None
        lead_doc = MagicMock()
        lead_doc.name = "LEAD-001"
        lead_doc.lead_name = "Rahul Sharma"
        lead_doc.first_name = "Rahul"
        lead_doc.last_name = "Sharma"
        lead_doc.mobile_no = "+919876543210"
        lead_doc.email = "rahul@example.com"

        with patch("frappe.get_meta") as mock_meta, patch("visa_crm.api.deal_sync.ensure_contact_for_deal"):
            mock_deal_meta = MagicMock()
            mock_deal_meta.has_field.return_value = True
            mock_meta.return_value = mock_deal_meta

            updated = map_lead_to_deal(deal_doc, lead_doc)
            self.assertIn("lead_name", updated)
            self.assertEqual(deal_doc.lead_name, "Rahul Sharma")

    def test_02_lead_to_deal_mobile_mapping(self):
        """2. Lead -> Deal mobile mapping."""
        deal_doc = MagicMock()
        deal_doc.mobile_no = None
        deal_doc.phone = None
        lead_doc = MagicMock()
        lead_doc.name = "LEAD-002"
        lead_doc.lead_name = "Priya Patel"
        lead_doc.mobile_no = "+919123456789"
        lead_doc.phone = None
        lead_doc.email = None

        with patch("frappe.get_meta") as mock_meta, patch("visa_crm.api.deal_sync.ensure_contact_for_deal"):
            mock_deal_meta = MagicMock()
            mock_deal_meta.has_field.return_value = True
            mock_meta.return_value = mock_deal_meta

            updated = map_lead_to_deal(deal_doc, lead_doc)
            self.assertIn("mobile_no", updated)
            self.assertEqual(deal_doc.mobile_no, "+919123456789")

    def test_03_existing_valid_mobile_preserved(self):
        """3. Existing valid mobile is not unnecessarily overwritten."""
        deal_doc = MagicMock()
        deal_doc.mobile_no = "+971501112233"  # Existing valid
        lead_doc = MagicMock()
        lead_doc.name = "LEAD-003"
        lead_doc.mobile_no = "+919888877777"

        with patch("frappe.get_meta") as mock_meta, patch("visa_crm.api.deal_sync.ensure_contact_for_deal"):
            mock_deal_meta = MagicMock()
            mock_deal_meta.has_field.return_value = True
            mock_meta.return_value = mock_deal_meta

            updated = map_lead_to_deal(deal_doc, lead_doc, overwrite_existing=False)
            self.assertNotIn("mobile_no", updated)
            self.assertEqual(deal_doc.mobile_no, "+971501112233")

    def test_04_missing_contact_handled(self):
        """4. Missing Contact is handled gracefully without crash."""
        deal_doc = MagicMock()
        deal_doc.contacts = []
        deal_doc.contact = None
        lead_doc = MagicMock()
        lead_doc.name = "LEAD-004"
        lead_doc.lead_name = "New Contact Lead"
        lead_doc.mobile_no = "+919555544444"
        lead_doc.email = "new@example.com"

        mock_contact = MagicMock()
        mock_contact.name = "CON-NEW-001"

        with patch("frappe.db.get_value", return_value=None),              patch("frappe.new_doc", return_value=mock_contact):
            res = ensure_contact_for_deal(deal_doc, lead_doc)
            self.assertEqual(res, "CON-NEW-001")
            self.assertEqual(deal_doc.contact, "CON-NEW-001")
            mock_contact.insert.assert_called_once()

    def test_05_existing_contact_reused(self):
        """5. Existing Contact is reused without creating a new one."""
        deal_doc = MagicMock()
        deal_doc.contacts = []
        deal_doc.contact = None
        lead_doc = MagicMock()
        lead_doc.name = "LEAD-005"
        lead_doc.lead_name = "Existing Person"
        lead_doc.mobile_no = "+919444433333"
        lead_doc.email = "exist@example.com"

        # Dynamic link exists
        with patch("frappe.db.get_value", return_value="CON-EXIST-099"),              patch("frappe.db.exists", return_value=True),              patch("frappe.new_doc") as mock_new_doc:
            res = ensure_contact_for_deal(deal_doc, lead_doc)
            self.assertEqual(res, "CON-EXIST-099")
            mock_new_doc.assert_not_called()

    def test_06_duplicate_contact_not_created(self):
        """6. Duplicate Contact is not created when phone matches Contact Phone."""
        deal_doc = MagicMock()
        deal_doc.contacts = []
        deal_doc.contact = None
        lead_doc = MagicMock()
        lead_doc.name = "LEAD-006"
        lead_doc.lead_name = "Phone Match"
        lead_doc.mobile_no = "+919333322222"
        lead_doc.email = None

        # Simulate Contact Phone match
        def mock_get_val(dt, filters, field):
            if dt == "Contact Phone":
                return "CON-BY-PHONE"
            return None

        with patch("frappe.db.get_value", side_effect=mock_get_val),              patch("frappe.db.exists", return_value=False),              patch("frappe.new_doc") as mock_new_doc:
            res = ensure_contact_for_deal(deal_doc, lead_doc)
            self.assertEqual(res, "CON-BY-PHONE")
            mock_new_doc.assert_not_called()

    def test_07_missing_lead_handled(self):
        """7. Missing Lead is handled gracefully."""
        deal_doc = MagicMock()
        deal_doc.lead = None
        updated = map_lead_to_deal(deal_doc, None)
        self.assertEqual(updated, [])

        res = ensure_contact_for_deal(deal_doc, None)
        self.assertIsNone(res)

    def test_08_missing_lead_mobile_handled(self):
        """8. Missing Lead mobile is handled safely."""
        deal_doc = MagicMock()
        deal_doc.lead_name = None
        deal_doc.mobile_no = None
        deal_doc.phone = None
        lead_doc = MagicMock()
        lead_doc.name = "LEAD-008"
        lead_doc.lead_name = "No Phone"
        lead_doc.mobile_no = None
        lead_doc.phone = None
        lead_doc.email = "nophone@example.com"

        with patch("frappe.get_meta") as mock_meta, patch("visa_crm.api.deal_sync.ensure_contact_for_deal"):
            mock_deal_meta = MagicMock()
            mock_deal_meta.has_field.return_value = True
            mock_meta.return_value = mock_deal_meta

            updated = map_lead_to_deal(deal_doc, lead_doc)
            self.assertNotIn("mobile_no", updated)
            self.assertIn("lead_name", updated)

    def test_09_missing_lead_name_handled(self):
        """9. Missing Lead name is synthesized from first/last name or left clean."""
        deal_doc = MagicMock()
        deal_doc.lead_name = None
        lead_doc = MagicMock()
        lead_doc.name = "LEAD-009"
        lead_doc.lead_name = None
        lead_doc.first_name = "John"
        lead_doc.last_name = "Smith"
        lead_doc.mobile_no = "+919000011111"
        lead_doc.email = None

        with patch("frappe.get_meta") as mock_meta, patch("visa_crm.api.deal_sync.ensure_contact_for_deal"):
            mock_deal_meta = MagicMock()
            mock_deal_meta.has_field.return_value = True
            mock_meta.return_value = mock_deal_meta

            updated = map_lead_to_deal(deal_doc, lead_doc)
            self.assertIn("lead_name", updated)
            self.assertEqual(deal_doc.lead_name, "John Smith")

    def test_10_meta_campaign_data_intact(self):
        """10. Meta campaign data remains intact."""
        deal_doc = MagicMock()
        deal_doc.custom_meta_campaign_name = None
        deal_doc.custom_meta_adset_name = None
        deal_doc.custom_lead_category = None
        deal_doc.custom_destination = None

        lead_doc = MagicMock()
        lead_doc.name = "LEAD-010"
        lead_doc.lead_name = "Campaign User"
        lead_doc.meta_campaign_name = "Thailand Leads campaign"
        lead_doc.meta_adset_name = "calicut"
        lead_doc.lead_category = "Holidays"
        lead_doc.custom_destination = "Thailand"
        lead_doc.mobile_no = "+919035792321"

        with patch("frappe.get_meta") as mock_meta, patch("visa_crm.api.deal_sync.ensure_contact_for_deal"):
            mock_deal_meta = MagicMock()
            mock_deal_meta.has_field.return_value = True
            mock_meta.return_value = mock_deal_meta

            updated = map_lead_to_deal(deal_doc, lead_doc)
            self.assertIn("custom_meta_campaign_name", updated)
            self.assertEqual(deal_doc.custom_meta_campaign_name, "Thailand Leads campaign")
            self.assertEqual(deal_doc.custom_meta_adset_name, "calicut")
            self.assertEqual(deal_doc.custom_lead_category, "Holidays")
            self.assertEqual(deal_doc.custom_destination, "Thailand")

    def test_11_sync_idempotency(self):
        """11. Re-running sync is idempotent."""
        deal_doc = MagicMock()
        deal_doc.lead_name = None
        deal_doc.mobile_no = None

        lead_doc = MagicMock()
        lead_doc.name = "LEAD-011"
        lead_doc.lead_name = "Idempotent Lead"
        lead_doc.mobile_no = "+919999900000"

        with patch("frappe.get_meta") as mock_meta, patch("visa_crm.api.deal_sync.ensure_contact_for_deal"):
            mock_deal_meta = MagicMock()
            mock_deal_meta.has_field.return_value = True
            mock_meta.return_value = mock_deal_meta

            # First run: updates fields
            updated_1 = map_lead_to_deal(deal_doc, lead_doc, overwrite_existing=False)
            self.assertIn("lead_name", updated_1)
            self.assertIn("mobile_no", updated_1)

            # Second run: no updates (idempotent)
            updated_2 = map_lead_to_deal(deal_doc, lead_doc, overwrite_existing=False)
            self.assertEqual(updated_2, [])

    def test_12_new_deal_creation_workflow(self):
        """12. New Deal creation from workflow sets lead_name, mobile_no, and links Contact."""
        from visa_crm.api.workflow import create_deal_if_supported

        mock_lead = MagicMock()
        mock_lead.name = "LEAD-WF-001"
        mock_lead.lead_name = "Workflow Lead"
        mock_lead.mobile_no = "+919876543210"
        mock_lead.email = "wf@example.com"

        mock_deal = MagicMock()
        mock_deal.name = "DEAL-WF-001"
        mock_deal.contacts = []

        def mock_exists(dt, name=None):
            if dt == "DocType" and name == "CRM Deal":
                return True
            if dt == "CRM Deal":
                return None
            if dt == "CRM Lead":
                return True
            return False

        with patch("frappe.db.exists", side_effect=mock_exists),              patch("frappe.get_meta") as mock_meta,              patch("frappe.get_doc", return_value=mock_lead),              patch("frappe.new_doc", return_value=mock_deal),              patch("visa_crm.api.workflow._ensure_link_master"),              patch("visa_crm.api.deal_sync.ensure_contact_for_deal"):
            mock_meta_inst = MagicMock()
            mock_meta_inst.has_field.return_value = True
            mock_meta.return_value = mock_meta_inst

            deal_name = create_deal_if_supported("LEAD-WF-001", {"customer_name": "Workflow Lead", "phone": "+919876543210"})
            self.assertEqual(deal_name, "DEAL-WF-001")
            self.assertEqual(mock_deal.lead_name, "Workflow Lead")
            self.assertEqual(mock_deal.mobile_no, "+919876543210")
            mock_deal.insert.assert_called_once()

    def test_13_audit_and_backfill_deals_dry_run(self):
        """13. Existing Deal backfill runs safely in dry-run mode."""
        mock_deal = MagicMock()
        mock_deal.name = "DEAL-DRY-01"
        mock_deal.lead = "LEAD-DRY-01"
        mock_deal.lead_name = None
        mock_deal.mobile_no = None

        mock_lead = MagicMock()
        mock_lead.name = "LEAD-DRY-01"
        mock_lead.lead_name = "Dry Run User"
        mock_lead.mobile_doc = "+919222211111"

        with patch("frappe.get_all", return_value=["DEAL-DRY-01"]),              patch("frappe.get_doc", side_effect=[mock_deal, mock_lead]),              patch("frappe.db.exists", return_value=True),              patch("frappe.get_meta") as mock_meta,              patch("visa_crm.api.deal_sync.ensure_contact_for_deal"):
            mock_deal_meta = MagicMock()
            mock_deal_meta.has_field.return_value = True
            mock_meta.return_value = mock_deal_meta

            report = audit_and_backfill_deals(dry_run=True)
            self.assertEqual(report["mode"], "DRY_RUN")
            self.assertEqual(report["total_deals_examined"], 1)
            self.assertEqual(report["deals_requiring_update"], 1)
            mock_deal.save.assert_not_called()  # Dry run must NOT save

    def test_14_list_enrichment_returns_customer_mobile(self):
        """14. List enrichment returns customer/mobile correctly."""
        deal_rows = [
            {
                "name": "DEAL-ENRICH-01",
                "lead": "LEAD-ENRICH-01",
                "lead_name": None,
                "mobile_no": "",
                "email": "",
            }
        ]

        mock_lead = MagicMock()
        mock_lead.name = "LEAD-ENRICH-01"
        mock_lead.lead_name = "Batch Enriched"
        mock_lead.first_name = "Batch"
        mock_lead.last_name = "Enriched"
        mock_lead.mobile_no = "+919999888877"
        mock_lead.phone = "+919999888877"
        mock_lead.email = "batch@example.com"
        mock_lead.meta_campaign_name = "Camp"
        mock_lead.meta_adset_name = "Adset"
        mock_lead.lead_category = "Cat"
        mock_lead.responsible_department = "Dept"
        mock_lead.custom_destination = "Dest"

        with patch("frappe.get_all", return_value=[mock_lead]):
            enriched = enrich_deal_list_data(deal_rows)
            self.assertEqual(enriched[0]["lead_name"], "Batch Enriched")
            self.assertEqual(enriched[0]["mobile_no"], "+919999888877")
            self.assertEqual(enriched[0]["email"], "batch@example.com")

    def test_15_no_recursive_save_behavior(self):
        """15. No recursive save behavior in after_save hook."""
        mock_lead = MagicMock()
        mock_lead.name = "LEAD-RECURSE-01"

        mock_deal = MagicMock()
        mock_deal.name = "DEAL-RECURSE-01"
        mock_deal.flags = MagicMock()

        with patch("frappe.db.exists", return_value=True),              patch("frappe.get_all", return_value=["DEAL-RECURSE-01"]),              patch("frappe.get_doc", return_value=mock_deal),              patch("visa_crm.api.deal_sync.map_lead_to_deal", return_value=["lead_name"]):
            sync_lead_to_linked_deal_after_save(mock_lead)
            mock_deal.save.assert_called_once()
            self.assertTrue(mock_deal.flags.ignore_permissions)


if __name__ == "__main__":
    unittest.main()
