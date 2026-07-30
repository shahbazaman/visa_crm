import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date,now_datetime
from visa_crm.api.pipeline_engine import claim_stage,complete_stage,ensure_stage_ledger,recover_expired_leases,retry_stage,rollup_queue,run_stage,stage_key

class TestPipelineEngine(FrappeTestCase):
    def setUp(self):
        self.queue=self._queue()
        ensure_stage_ledger(self.queue)
        frappe.db.commit()

    def tearDown(self):
        frappe.db.delete("Lead Intake Stage",{"queue":self.queue})
        frappe.db.delete("Lead Intake Queue",{"name":self.queue})
        frappe.db.commit()

    def test_claim_is_atomic_and_completion_is_durable(self):
        first=claim_stage(self.queue,"GRAPH_DOWNLOAD")
        self.assertTrue(first)
        self.assertIsNone(claim_stage(self.queue,"GRAPH_DOWNLOAD"))
        complete_stage(first,result={"downloaded":True})
        frappe.db.commit()
        row=frappe.db.get_value("Lead Intake Stage",first.name,["state","attempt_count","result_json"],as_dict=True)
        self.assertEqual(row.state,"COMPLETED")
        self.assertEqual(row.attempt_count,1)
        self.assertIn("downloaded",row.result_json)

    def test_failure_rolls_back_only_active_stage_and_retries(self):
        marker={"called":0}
        def fail(_queue,_claim):
            marker["called"]+=1
            raise RuntimeError("isolated stage failure")
        result=run_stage(self.queue,fail,stage="GRAPH_DOWNLOAD")
        self.assertFalse(result.ok)
        row=frappe.db.get_value("Lead Intake Stage",stage_key(self.queue,"GRAPH_DOWNLOAD"),["state","last_error_class","next_retry_at"],as_dict=True)
        self.assertEqual(row.state,"FAILED")
        self.assertIn("RuntimeError",row.last_error_class)
        self.assertTrue(row.next_retry_at)
        self.assertTrue(retry_stage(self.queue,"GRAPH_DOWNLOAD"))
        claim=claim_stage(self.queue,"GRAPH_DOWNLOAD")
        self.assertTrue(claim)
        self.assertEqual(claim.attempt_count,2)

    def test_stale_worker_lease_is_recovered(self):
        claim=claim_stage(self.queue,"GRAPH_DOWNLOAD")
        frappe.db.set_value("Lead Intake Stage",claim.name,"lease_expires_at",add_to_date(now_datetime(),minutes=-1),update_modified=False)
        frappe.db.commit()
        queues,stages=recover_expired_leases()
        self.assertEqual((queues,stages),(1,1))
        row=frappe.db.get_value("Lead Intake Stage",claim.name,["state","last_error_class"],as_dict=True)
        self.assertEqual(row.state,"FAILED")
        self.assertEqual(row.last_error_class,"WorkerLeaseExpired")
        self.assertTrue(claim_stage(self.queue,"GRAPH_DOWNLOAD"))

    def test_completed_lead_survives_optional_failure_rollup(self):
        self._complete_through("CRM_LEAD")
        claim=claim_stage(self.queue,"COUNSELOR_ASSIGNMENT")
        self.assertTrue(claim)
        from visa_crm.api.pipeline_engine import fail_stage
        fail_stage(claim,RuntimeError("No eligible counselor configured"))
        frappe.db.commit()
        rollup=rollup_queue(self.queue)
        self.assertEqual(rollup.status,"COMPLETED_WITH_WARNINGS")
        self.assertEqual(frappe.db.get_value("Lead Intake Queue",self.queue,"status"),"Processed With Warnings")
        self.assertEqual(frappe.db.get_value("Lead Intake Stage",stage_key(self.queue,"CRM_LEAD"),"state"),"COMPLETED")

    def _complete_through(self,last_stage):
        for stage in ("GRAPH_DOWNLOAD","NORMALIZE","CUSTOMER360","CRM_LEAD"):
            claim=claim_stage(self.queue,stage)
            self.assertTrue(claim)
            complete_stage(claim,result={"stage":stage})
            frappe.db.commit()
            if stage==last_stage:
                break

    def _queue(self):
        doc=frappe.new_doc("Lead Intake Queue")
        doc.source_lead_id=f"ENGINE-{frappe.generate_hash(length=10)}"
        doc.status="Lead Received"
        doc.raw_payload="{}"
        doc.insert(ignore_permissions=True)
        return doc.name
