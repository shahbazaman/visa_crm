from unittest.mock import patch
import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api.pipeline_engine import complete_stage,claim_stage,ensure_stage_ledger
from visa_crm.api.pipeline_stage_services import graph_download,normalize

class TestPipelineIngestionStages(FrappeTestCase):
    def setUp(self):
        doc=frappe.new_doc("Lead Intake Queue")
        doc.source_lead_id=f"GRAPH-{frappe.generate_hash(length=10)}"
        doc.status="Lead Received"
        doc.raw_payload="{}"
        doc.insert(ignore_permissions=True)
        self.queue=doc.name
        ensure_stage_ledger(self.queue)
        frappe.db.commit()

    def tearDown(self):
        frappe.db.delete("Lead Intake Stage",{"queue":self.queue})
        frappe.db.delete("Lead Intake Queue",{"name":self.queue})
        frappe.db.commit()

    def test_graph_snapshot_is_reused_without_second_download(self):
        payload={"id":self._source_id(),"field_data":[{"name":"full_name","values":["John Doe"]}]}
        with patch("visa_crm.api.pipeline_stage_services.fetch_lead",return_value=payload) as fetch:
            result=graph_download(self.queue)
            again=graph_download(self.queue)
        self.assertEqual(fetch.call_count,1)
        self.assertFalse(result["reused"])
        self.assertTrue(again["reused"])
        self.assertEqual(result["output_hash"],again["output_hash"])

    def test_normalize_uses_persisted_graph_and_is_reusable(self):
        payload={"id":self._source_id(),"form_id":"FORM-1","campaign_id":"CAM-1","campaign_name":"Campaign","field_data":[{"name":"full_name","values":["John Doe"]},{"name":"phone","values":["+971501234567"]},{"name":"email","values":["john@example.com"]}]}
        with patch("visa_crm.api.pipeline_stage_services.fetch_lead",return_value=payload):
            graph=graph_download(self.queue)
        graph_claim=claim_stage(self.queue,"GRAPH_DOWNLOAD")
        complete_stage(graph_claim,graph,input_hash=graph["input_hash"],output_hash=graph["output_hash"])
        frappe.db.commit()
        normalized=normalize(self.queue)
        again=normalize(self.queue)
        self.assertFalse(normalized["reused"])
        self.assertTrue(again["reused"])
        row=frappe.db.get_value("Lead Intake Queue",self.queue,["customer_name","phone","email","campaign_id","normalization_version","normalized_payload_hash"],as_dict=True)
        self.assertEqual(row.customer_name,"John Doe")
        self.assertEqual(row.phone,"+971501234567")
        self.assertEqual(row.email,"john@example.com")
        self.assertEqual(row.campaign_id,"CAM-1")
        self.assertTrue(row.normalization_version)
        self.assertEqual(row.normalized_payload_hash,normalized["output_hash"])

    def _source_id(self):
        return frappe.db.get_value("Lead Intake Queue",self.queue,"source_lead_id")
