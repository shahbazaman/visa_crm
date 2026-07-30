from unittest.mock import patch
import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api.pipeline_engine import ensure_stage_ledger,run_stage,stage_key
from visa_crm.api.pipeline_stage_services import assignment_failure,counselor_assignment,crm_lead,customer360

class TestPipelineAssignmentStage(FrappeTestCase):
    def setUp(self):
        suffix=frappe.generate_hash(length=10)
        self.source=f"ASSIGN-{suffix}"
        data={"source_lead_id":self.source,"customer_name":f"Assignment {suffix}","email":f"{suffix}@example.com","meta_fields":{"full_name":f"Assignment {suffix}"},"meta_raw_fields":"{}"}
        doc=frappe.new_doc("Lead Intake Queue")
        doc.source_lead_id=self.source
        doc.status="Lead Downloaded"
        doc.raw_payload="{}"
        doc.normalized_payload=frappe.as_json(data)
        doc.normalized_payload_hash=frappe.generate_hash(length=32)
        doc.insert(ignore_permissions=True)
        self.queue=doc.name
        ensure_stage_ledger(self.queue)
        customer360(self.queue)
        crm_lead(self.queue)
        for stage in ("GRAPH_DOWNLOAD","NORMALIZE","CUSTOMER360","CRM_LEAD","LEAD_WORKFLOW","VISA_APPLICATION","COMMUNICATION_EVENT","FOLLOW_UP"):
            frappe.db.set_value("Lead Intake Stage",stage_key(self.queue,stage),"state","COMPLETED",update_modified=False)
        frappe.db.commit()

    def tearDown(self):
        queue=frappe.get_doc("Lead Intake Queue",self.queue)
        frappe.db.delete("Lead Intake Stage",{"queue":self.queue})
        frappe.db.delete("Customer Identity",{"customer":queue.matched_customer})
        frappe.db.delete("CRM Lead",{"name":queue.matched_lead})
        frappe.db.delete("Customer",{"name":queue.matched_customer})
        frappe.db.delete("Lead Intake Queue",{"name":self.queue})
        frappe.db.commit()

    def test_no_counselor_fails_only_assignment_stage(self):
        with patch("visa_crm.api.lead_assignment._eligible_employees",return_value=[]):
            result=run_stage(self.queue,counselor_assignment,stage="COUNSELOR_ASSIGNMENT",failure_handler=assignment_failure)
        self.assertFalse(result.ok)
        queue=frappe.get_doc("Lead Intake Queue",self.queue)
        self.assertTrue(frappe.db.exists("CRM Lead",queue.matched_lead))
        self.assertTrue(frappe.db.exists("Customer",queue.matched_customer))
        self.assertEqual(frappe.db.get_value("Lead Intake Stage",stage_key(self.queue,"COUNSELOR_ASSIGNMENT"),"state"),"FAILED")
        self.assertEqual(frappe.db.get_value("CRM Lead",queue.matched_lead,"assignment_status"),"Needs Assignment")
        self.assertEqual(queue.orchestration_status,"COMPLETED_WITH_WARNINGS")
        self.assertEqual(queue.status,"Processed With Warnings")
