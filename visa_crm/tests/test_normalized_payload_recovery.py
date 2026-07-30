from unittest.mock import patch
import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api import intake_processor
from visa_crm.api.pipeline_engine import claim_stage,complete_stage,ensure_stage_ledger,repair_normalization_checkpoint,stage_key
from visa_crm.api.pipeline_stage_services import customer360,load_normalized,normalize
from visa_crm.patches.repair_normalized_payload_checkpoints import execute as repair_patch

class TestNormalizedPayloadRecovery(FrappeTestCase):
    def setUp(self):
        self.source=f"RECOVERY-{frappe.generate_hash(length=10)}"
        self.payload={"id":self.source,"form_id":"FORM-RECOVERY","page_id":"PAGE-RECOVERY","campaign_id":"CAM-RECOVERY","campaign_name":"Recovery Campaign","field_data":[{"name":"full_name","values":["Recovery Lead"]},{"name":"phone","values":["+971501234567"]},{"name":"email","values":["recovery@example.com"]}]}
        doc=frappe.new_doc("Lead Intake Queue")
        doc.update({"source_lead_id":self.source,"status":"Lead Downloaded","raw_payload":"{}","graph_payload":frappe.as_json(self.payload),"graph_api_response":frappe.as_json(self.payload),"custom_answers":frappe.as_json({"full_name":"Recovery Lead","phone":"+971501234567","email":"recovery@example.com"})})
        doc.insert(ignore_permissions=True)
        self.queue=doc.name
        ensure_stage_ledger(self.queue)
        self._complete("GRAPH_DOWNLOAD")
        self._complete("NORMALIZE")
        frappe.db.set_value("Lead Intake Stage",stage_key(self.queue,"CUSTOMER360"),{"state":"FAILED","attempt_count":5,"max_attempts":5,"last_error":"Normalized payload is missing for queue "+self.queue},update_modified=False)
        frappe.db.commit()

    def tearDown(self):
        customer=frappe.db.get_value("Lead Intake Queue",self.queue,"matched_customer")
        frappe.db.delete("Lead Intake Stage",{"queue":self.queue})
        if customer:
            frappe.db.delete("Customer Identity",{"customer":customer})
            frappe.db.delete("Customer",{"name":customer})
        frappe.db.delete("Lead Intake Queue",{"name":self.queue})
        frappe.db.commit()

    def test_completed_normalize_checkpoint_is_repaired_after_reload(self):
        with patch("visa_crm.api.pipeline_stage_services.fetch_lead",side_effect=AssertionError("recovery must not call Graph API")):
            self.assertTrue(repair_normalization_checkpoint(self.queue))
            self.assertEqual(frappe.db.get_value("Lead Intake Stage",stage_key(self.queue,"NORMALIZE"),"state"),"NOT_STARTED")
            normalized=normalize(self.queue)
            frappe.db.commit()
            frappe.clear_cache()
            self.assertEqual(load_normalized(self.queue)["customer_name"],"Recovery Lead")
            claim=claim_stage(self.queue,"NORMALIZE")
            complete_stage(claim,normalized,input_hash=normalized["input_hash"],output_hash=normalized["output_hash"])
            frappe.db.commit()
            customer=customer360(self.queue)["customer"]
        self.assertTrue(frappe.db.exists("Customer",customer))
        self.assertEqual(frappe.db.get_value("Lead Intake Stage",stage_key(self.queue,"CUSTOMER360"),"max_attempts"),6)

    def test_normalized_payload_rebuilds_from_immutable_queue_answers_without_graph(self):
        frappe.db.set_value("Lead Intake Queue",self.queue,{"graph_payload":None,"graph_api_response":None,"normalized_payload":None,"normalized_payload_hash":None},update_modified=False)
        frappe.db.commit()
        with patch("visa_crm.api.pipeline_stage_services.fetch_lead",side_effect=AssertionError("recovery must not call Graph API")):
            data=load_normalized(self.queue)
        queue=frappe.db.get_value("Lead Intake Queue",self.queue,["normalized_payload","normalized_payload_hash","normalization_version"],as_dict=True)
        self.assertEqual(data["customer_name"],"Recovery Lead")
        self.assertTrue(queue.normalized_payload)
        self.assertTrue(queue.normalized_payload_hash)
        self.assertTrue(queue.normalization_version)

    def test_migration_repair_is_idempotent(self):
        repair_patch()
        first=frappe.db.get_value("Lead Intake Stage",stage_key(self.queue,"NORMALIZE"),"state")
        repair_patch()
        second=frappe.db.get_value("Lead Intake Stage",stage_key(self.queue,"NORMALIZE"),"state")
        self.assertEqual(first,"NOT_STARTED")
        self.assertEqual(second,"NOT_STARTED")

    def test_scheduler_path_repairs_then_retries_customer360_without_graph_download(self):
        customer=frappe.new_doc("Customer")
        customer.customer_name=f"Recovery Customer {self.source}"
        customer.insert(ignore_permissions=True)
        with patch("visa_crm.api.pipeline_stage_services.fetch_lead",side_effect=AssertionError("recovery must not call Graph API")),patch("visa_crm.api.pipeline_stage_services.resolve_customer",return_value=customer.name):
            intake_processor.process_queue(self.queue,stage_budget=2)
        self.assertEqual(frappe.db.get_value("Lead Intake Stage",stage_key(self.queue,"NORMALIZE"),"state"),"COMPLETED")
        self.assertEqual(frappe.db.get_value("Lead Intake Stage",stage_key(self.queue,"CUSTOMER360"),"state"),"COMPLETED")
        self.assertEqual(frappe.db.get_value("Lead Intake Queue",self.queue,"matched_customer"),customer.name)

    def _complete(self,stage):
        claim=claim_stage(self.queue,stage)
        complete_stage(claim,result={"stage":stage})
