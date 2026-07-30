import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api.stage_definitions import STAGES
from visa_crm.patches import create_meta_stage_orchestration as patch

class TestMetaStageSchema(FrappeTestCase):
    def test_stage_schema_and_backfill_are_idempotent(self):
        self.assertTrue(frappe.db.exists("DocType","Lead Intake Stage"))
        self.assertTrue(frappe.db.exists("DocType","Customer Identity"))
        before=frappe.db.count("Lead Intake Stage")
        patch.execute()
        first=frappe.db.count("Lead Intake Stage")
        patch.execute()
        second=frappe.db.count("Lead Intake Stage")
        self.assertGreaterEqual(first,before)
        self.assertEqual(second,first)
        for queue in frappe.get_all("Lead Intake Queue",pluck="name"):
            rows=frappe.get_all("Lead Intake Stage",filters={"queue":queue},pluck="stage")
            self.assertEqual(len(rows),len(STAGES))
            self.assertEqual(set(rows),{row["stage"] for row in STAGES})

    def test_attribution_backfill_only_populates_blank_fields(self):
        suffix=frappe.generate_hash(length=8)
        lead=frappe.new_doc("CRM Lead")
        for field,value in {"first_name":f"Attribution {suffix}","lead_name":f"Attribution {suffix}","facebook_lead_id":f"ATTR-{suffix}","meta_campaign_name":"Existing Campaign"}.items():
            if lead.meta.has_field(field):
                lead.set(field,value)
        lead.insert(ignore_permissions=True)
        queue=frappe.new_doc("Lead Intake Queue")
        queue.status="Lead Received"
        queue.source_lead_id=f"ATTR-{suffix}"
        queue.matched_lead=lead.name
        queue.campaign_id="CAM-BACKFILL"
        queue.campaign_name="Replacement Campaign"
        queue.ad_id="AD-BACKFILL"
        queue.insert(ignore_permissions=True)
        patch._backfill_attribution()
        lead.reload()
        self.assertEqual(lead.meta_campaign_name,"Existing Campaign")
        self.assertEqual(lead.meta_campaign_id,"CAM-BACKFILL")
        self.assertEqual(lead.meta_ad_id,"AD-BACKFILL")
