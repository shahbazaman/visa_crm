import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api.pipeline_engine import ensure_stage_ledger, run_stage, stages_for, rollup_queue, retry_stage
from visa_crm.api.intake_processor import process_queue
from visa_crm.api.recovery import retry_queue

class TestPipelineFailureIsolation(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.lead_id = f"ISOLATION-TEST-{frappe.generate_hash(length=8)}"
        self.queue = frappe.get_doc({
            "doctype": "Lead Intake Queue",
            "status": "Lead Downloaded",
            "lead_source": "Meta Instant Form",
            "source_lead_id": self.lead_id,
            "customer_name": "Stage Isolation Lead",
            "phone": "+19997775533",
            "email": "isolation.lead@example.com",
            "normalized_payload": frappe.as_json({
                "source_lead_id": self.lead_id,
                "customer_name": "Stage Isolation Lead",
                "phone": "+19997775533",
                "email": "isolation.lead@example.com",
                "campaign_name": "Meta Travel Campaign 2026",
                "campaign_id": "CAMP-991122",
                "country_interested": "USA",
                "visa_type": "Tourist"
            }),
            "normalized_payload_hash": "hash_isolation_1"
        })
        self.queue.insert(ignore_permissions=True)
        frappe.db.commit()

        ensure_stage_ledger(self.queue.name)
        for dep in ("WEBHOOK", "GRAPH_DOWNLOAD", "NORMALIZE", "CLASSIFICATION"):
            frappe.db.set_value("Lead Intake Stage", f"{self.queue.name}:{dep}", {"state": "COMPLETED"}, update_modified=False)
        frappe.db.commit()

    def test_stage_failure_does_not_rollback_completed_stages(self):
        def forced_c360_fail(qname, claim):
            raise ValueError("Simulated Customer360 Exception")

        outcome = run_stage(self.queue.name, forced_c360_fail, stage="CUSTOMER360")
        self.assertIsNotNone(outcome)
        self.assertFalse(outcome.ok)

        # 1. Verify early completed stages remain COMPLETED
        norm_state = frappe.db.get_value("Lead Intake Stage", f"{self.queue.name}:NORMALIZE", "state")
        self.assertEqual(norm_state, "COMPLETED")

        # 2. Verify CUSTOMER360 is FAILED and last_error is recorded
        c360_row = frappe.db.get_value("Lead Intake Stage", f"{self.queue.name}:CUSTOMER360", ["state", "last_error"], as_dict=True)
        self.assertEqual(c360_row.state, "FAILED")
        self.assertIn("Simulated Customer360 Exception", c360_row.last_error)

        # 3. Verify top-level Lead Intake Queue last_error is recorded
        q_err = frappe.db.get_value("Lead Intake Queue", self.queue.name, "last_error")
        self.assertIn("Simulated Customer360 Exception", q_err)

    def test_blocked_stage_status_and_unblocking_on_retry(self):
        def forced_c360_fail(qname, claim):
            raise ValueError("Simulated Customer360 Exception")

        run_stage(self.queue.name, forced_c360_fail, stage="CUSTOMER360")
        rollup_queue(self.queue.name)

        # Verify CRM_LEAD is BLOCKED due to CUSTOMER360 failure
        crm_stage = frappe.get_doc("Lead Intake Stage", f"{self.queue.name}:CRM_LEAD")
        self.assertEqual(crm_stage.state, "BLOCKED")
        self.assertIn("CUSTOMER360", crm_stage.skip_reason or "")

        # Now retry CUSTOMER360 cleanly
        frappe.set_user("Administrator")
        res = retry_queue(self.queue.name)
        self.assertTrue(res.get("ok"))

        # Verify CUSTOMER360 and CRM_LEAD are now COMPLETED
        c360_state = frappe.db.get_value("Lead Intake Stage", f"{self.queue.name}:CUSTOMER360", "state")
        crm_state = frappe.db.get_value("Lead Intake Stage", f"{self.queue.name}:CRM_LEAD", "state")
        self.assertEqual(c360_state, "COMPLETED")
        self.assertEqual(crm_state, "COMPLETED")

    def test_idempotent_stage_retry_does_not_duplicate_documents(self):
        frappe.set_user("Administrator")
        res1 = retry_queue(self.queue.name)
        cust1 = res1.get("customer")
        lead1 = res1.get("lead")
        visa1 = res1.get("visa_application")

        # Second retry
        res2 = retry_queue(self.queue.name)
        self.assertEqual(res2.get("customer"), cust1)
        self.assertEqual(res2.get("lead"), lead1)
        self.assertEqual(res2.get("visa_application"), visa1)
