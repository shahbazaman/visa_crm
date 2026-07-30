from unittest.mock import patch
import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api import intake_processor
from visa_crm.api.pipeline_engine import stage_key

class TestAIEnqueueIsolation(FrappeTestCase):
    def setUp(self):
        suffix=frappe.generate_hash(length=10)
        self.source=f"REDIS-{suffix}"
        phone=f"+9715{''.join(str(ord(char)%10) for char in suffix)[:8]}"
        self.graph={"id":self.source,"field_data":[{"name":"full_name","values":[f"Redis Offline {suffix}"]},{"name":"phone","values":[phone]},{"name":"email","values":[f"{suffix}@example.com"]}],"form_id":"FORM-REDIS"}
        doc=frappe.new_doc("Lead Intake Queue")
        doc.status="Lead Received"
        doc.source_lead_id=self.source
        doc.event_type="leadgen"
        doc.raw_payload=frappe.as_json({"change":{"field":"leadgen"},"value":{"leadgen_id":self.source}})
        doc.insert(ignore_permissions=True)
        self.queue=doc.name
        frappe.db.commit()

    def tearDown(self):
        queue=frappe.get_doc("Lead Intake Queue",self.queue)
        for doctype,filters in (("Lead Intake AI Job",{"queue":self.queue}),("ToDo",{"meta_intake_key":f"followup:{self.queue}"}),("Communication Event",{"event_id":f"meta:{self.source}"}),("Visa Application",{"meta_intake_key":f"visa:{self.queue}"}),("Customer Identity",{"customer":queue.get("matched_customer")}),("CRM Lead",{"name":queue.get("matched_lead")}),("Customer",{"name":queue.get("matched_customer")}),("Lead Intake Stage",{"queue":self.queue}),("Lead Intake Queue",{"name":self.queue})):
            if frappe.db.exists("DocType",doctype):
                frappe.db.delete(doctype,filters)
        frappe.db.commit()

    def test_redis_offline_does_not_fail_mandatory_pipeline(self):
        employee=frappe.get_all("Employee",pluck="name",limit=1)[0]
        with patch("visa_crm.api.pipeline_stage_services.fetch_lead",return_value=self.graph),patch("visa_crm.api.pipeline_stage_services.assign_lead",return_value=employee),patch("visa_crm.api.pipeline_stage_services.frappe.enqueue",side_effect=ConnectionRefusedError("Redis offline")):
            result=intake_processor.process_queue(self.queue)
        queue=frappe.get_doc("Lead Intake Queue",self.queue)
        self.assertTrue(result["ok"])
        self.assertEqual(queue.status,"Processed")
        self.assertEqual(queue.orchestration_status,"COMPLETED")
        self.assertEqual(queue.ai_status,"Failed")
        self.assertIn("Redis offline",queue.ai_error)
        for doctype,name in (("CRM Lead",queue.matched_lead),("Customer",queue.matched_customer),("Visa Application",queue.visa_application),("Communication Event",queue.communication_event),("ToDo",queue.followup_reference)):
            self.assertTrue(frappe.db.exists(doctype,name),f"{doctype} was rolled back")
        self.assertEqual(frappe.db.get_value("Lead Intake Stage",stage_key(self.queue,"AI_DISPATCH"),"state"),"COMPLETED")
        self.assertEqual(frappe.db.get_value("Lead Intake AI Job",{"queue":self.queue},"state"),"FAILED")
        for stage in ("CRM_LEAD","VISA_APPLICATION","COMMUNICATION_EVENT","FOLLOW_UP","COUNSELOR_ASSIGNMENT"):
            self.assertEqual(frappe.db.get_value("Lead Intake Stage",stage_key(self.queue,stage),"state"),"COMPLETED")
