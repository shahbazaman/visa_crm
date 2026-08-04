from unittest.mock import patch
import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api import intake_processor
from visa_crm.api.pipeline_engine import retry_stage,run_stage,stage_key
from visa_crm.api.pipeline_stage_services import create_for_lead as real_create_visa

class TestPipelineResume(FrappeTestCase):
    def setUp(self):
        suffix=frappe.generate_hash(length=10)
        self.source=f"RESUME-{suffix}"
        self.phone=f"+9715{''.join(str(ord(char)%10) for char in suffix)[:8]}"
        self.graph={"id":self.source,"field_data":[{"name":"full_name","values":[f"Resume Lead {suffix}"]},{"name":"phone","values":[self.phone]},{"name":"email","values":[f"{suffix}@example.com"]}],"form_id":"FORM-RESUME","campaign_id":"CAM-RESUME"}
        doc=frappe.new_doc("Lead Intake Queue")
        doc.update({"status":"Lead Received","source_lead_id":self.source,"event_type":"leadgen","raw_payload":frappe.as_json({"change":{"field":"leadgen"},"value":{"leadgen_id":self.source}})})
        doc.insert(ignore_permissions=True)
        self.queue=doc.name
        frappe.db.commit()

    def tearDown(self):
        queue=frappe.get_doc("Lead Intake Queue",self.queue)
        lead=queue.get("matched_lead")
        customer=queue.get("matched_customer")
        for doctype,filters in (("Lead Intake AI Job",{"queue":self.queue}),("Lead Assignment",{"lead_intake_queue":self.queue}),("Lead Timeline",{"meta_intake_key":["like",f"%:{self.queue}"]}),("Activity Timeline",{"meta_intake_key":f"activity:{self.queue}"}),("Reminder Scheduler",{"meta_intake_key":f"reminder:{self.queue}"}),("ToDo",{"meta_intake_key":["like",f"%:{self.queue}"]}),("Communication Event",{"event_id":f"meta:{self.source}"}),("Visa Application",{"meta_intake_key":f"visa:{self.queue}"}),("Customer Identity",{"customer":customer}),("CRM Lead",{"name":lead}),("Customer",{"name":customer}),("Lead Intake Stage",{"queue":self.queue}),("Lead Intake Queue",{"name":self.queue})):
            if frappe.db.exists("DocType",doctype):
                frappe.db.delete(doctype,filters)
        frappe.db.commit()

    def test_worker_restart_after_each_stage_resumes_without_duplicates(self):
        employee=frappe.get_all("Employee",pluck="name",limit=1)[0]
        with patch("visa_crm.api.pipeline_stage_services.fetch_lead",return_value=self.graph) as fetch,patch("visa_crm.api.pipeline_stage_services.assign_lead",return_value=employee),patch("visa_crm.api.pipeline_stage_services.frappe.enqueue") as enqueue:
            for _ in range(11):
                intake_processor.process_queue(self.queue,stage_budget=1)
            intake_processor.process_queue(self.queue,stage_budget=1)
        queue=frappe.get_doc("Lead Intake Queue",self.queue)
        self.assertEqual(queue.status,"Processed")
        self.assertEqual(fetch.call_count,1)
        self.assertEqual(enqueue.call_count,1)
        self.assertEqual(frappe.db.count("CRM Lead",{"facebook_lead_id":self.source}),1)
        self.assertEqual(frappe.db.count("Visa Application",{"meta_intake_key":f"visa:{self.queue}"}),1)
        self.assertEqual(frappe.db.count("Communication Event",{"event_id":f"meta:{self.source}"}),1)
        self.assertEqual(frappe.db.count("ToDo",{"meta_intake_key":f"followup:{self.queue}"}),1)
        self.assertEqual(frappe.db.count("Lead Intake AI Job",{"queue":self.queue}),1)

    def test_visa_failure_resumes_from_visa_without_recreating_lead(self):
        employee=frappe.get_all("Employee",pluck="name",limit=1)[0]
        with patch("visa_crm.api.pipeline_stage_services.fetch_lead",return_value=self.graph) as fetch,patch("visa_crm.api.pipeline_stage_services.assign_lead",return_value=employee),patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"):
            intake_processor.process_queue(self.queue,stage_budget=6)
            lead=frappe.db.get_value("Lead Intake Queue",self.queue,"matched_lead")
            customer=frappe.db.get_value("Lead Intake Queue",self.queue,"matched_customer")
            with patch("visa_crm.api.pipeline_stage_services.create_for_lead",side_effect=RuntimeError("Visa service offline")):
                failed=intake_processor.process_queue(self.queue,stage_budget=1)
            self.assertEqual(failed["orchestration_status"],"PARTIALLY_COMPLETED")
            self.assertTrue(frappe.db.exists("CRM Lead",lead))
            self.assertTrue(frappe.db.exists("Customer",customer))
            self.assertTrue(retry_stage(self.queue,"VISA_APPLICATION"))
            with patch("visa_crm.api.pipeline_stage_services.create_for_lead",side_effect=real_create_visa):
                recovered=intake_processor.process_queue(self.queue)
        self.assertTrue(recovered["ok"])
        self.assertEqual(fetch.call_count,1)
        self.assertEqual(frappe.db.count("CRM Lead",{"facebook_lead_id":self.source}),1)
        self.assertEqual(frappe.db.count("Visa Application",{"meta_intake_key":f"visa:{self.queue}"}),1)
        self.assertEqual(frappe.db.get_value("Lead Intake Stage",stage_key(self.queue,"VISA_APPLICATION"),"attempt_count"),2)

    def test_graph_failure_retries_graph_then_completes_once(self):
        employee=frappe.get_all("Employee",pluck="name",limit=1)[0]
        with patch("visa_crm.api.pipeline_stage_services.fetch_lead",side_effect=RuntimeError("Graph unavailable")):
            failed=intake_processor.process_queue(self.queue,stage_budget=1)
        self.assertEqual(failed["orchestration_status"],"FAILED")
        self.assertFalse(frappe.db.get_value("Lead Intake Queue",self.queue,"matched_lead"))
        self.assertTrue(retry_stage(self.queue,"GRAPH_DOWNLOAD"))
        with patch("visa_crm.api.pipeline_stage_services.fetch_lead",return_value=self.graph),patch("visa_crm.api.pipeline_stage_services.assign_lead",return_value=employee),patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"):
            recovered=intake_processor.process_queue(self.queue)
        self.assertTrue(recovered["ok"])
        self.assertEqual(frappe.db.count("CRM Lead",{"facebook_lead_id":self.source}),1)
        self.assertEqual(frappe.db.get_value("Lead Intake Stage",stage_key(self.queue,"GRAPH_DOWNLOAD"),"attempt_count"),2)

    def test_communication_failure_preserves_lead_and_visa_then_resumes(self):
        employee=frappe.get_all("Employee",pluck="name",limit=1)[0]
        with patch("visa_crm.api.pipeline_stage_services.fetch_lead",return_value=self.graph),patch("visa_crm.api.pipeline_stage_services.assign_lead",return_value=employee),patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"):
            intake_processor.process_queue(self.queue,stage_budget=7)
            queue=frappe.get_doc("Lead Intake Queue",self.queue)
            result=run_stage(self.queue,lambda _queue,_claim:(_ for _ in ()).throw(RuntimeError("Communication unavailable")),stage="COMMUNICATION_EVENT")
            self.assertFalse(result.ok)
            self.assertTrue(frappe.db.exists("CRM Lead",queue.matched_lead))
            self.assertTrue(frappe.db.exists("Visa Application",queue.visa_application))
            self.assertTrue(retry_stage(self.queue,"COMMUNICATION_EVENT"))
            recovered=intake_processor.process_queue(self.queue)
        self.assertTrue(recovered["ok"])
        self.assertEqual(frappe.db.count("Communication Event",{"event_id":f"meta:{self.source}"}),1)
        self.assertEqual(frappe.db.count("CRM Lead",{"facebook_lead_id":self.source}),1)
