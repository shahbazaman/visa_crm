import json
import time
import unittest
import frappe
from frappe.utils.safe_exec import safe_exec
from visa_crm.api import meta_graph, pipeline_stage_services, intake_processor, pipeline_engine, recovery
from visa_crm.api.stage_definitions import STAGE_BY_NAME
from visa_crm.patches import fix_meta_access_token_length

class TestMetaPipelineHardening(unittest.TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        fix_meta_access_token_length.execute()

    def test_lead_fields_does_not_contain_page_id(self):
        fields = meta_graph.LEAD_FIELDS.split(",")
        self.assertNotIn("page_id", fields, "page_id must NOT be requested from Meta Graph API Lead node")
        self.assertIn("id", fields)
        self.assertIn("field_data", fields)
        self.assertIn("form_id", fields)

    def test_customer360_depends_on_normalize(self):
        c360_deps = STAGE_BY_NAME["CUSTOMER360"]["dependencies"]
        self.assertIn("NORMALIZE", c360_deps, "CUSTOMER360 must explicitly depend on NORMALIZE")

    def test_request_sanitization(self):
        req_struct = pipeline_stage_services._graph_request("1234567890123")
        self.assertNotIn("access_token", req_struct.get("params", {}), "graph_api_request params must NOT contain access_token")

    def test_meta_settings_token_length_capacity(self):
        if not frappe.db.exists("DocType", "Meta Settings"):
            return
        meta = frappe.get_meta("Meta Settings")
        field = meta.get_field("access_token")
        self.assertIsNotNone(field)
        self.assertGreaterEqual(int(field.length or 0), 400, "access_token field length must be at least 400")

    def test_safe_exec_recovery_invocation(self):
        # Test that System Console safe_exec can invoke retry_queue via frappe.call
        test_lead_id = f"998{int(time.time())}123"
        queue = frappe.get_doc({
            "doctype": "Lead Intake Queue",
            "source_lead_id": test_lead_id,
            "status": "Failed"
        }).insert(ignore_permissions=True)

        pipeline_engine.ensure_stage_ledger(queue.name)
        frappe.db.set_value("Lead Intake Stage", f"{queue.name}:GRAPH_DOWNLOAD", {"state": "FAILED"})

        snippet = f'frappe.call("visa_crm.api.recovery.retry_queue", queue_name="{queue.name}")'
        safe_exec(snippet)

        stages = dict(frappe.get_all("Lead Intake Stage", filters={"queue": queue.name}, fields=["stage", "state"], as_list=True))
        self.assertIn("GRAPH_DOWNLOAD", stages, "Stage ledger must be accessible after recovery call")
        frappe.db.rollback()

    def test_unauthorized_user_blocked(self):
        # Test that non-System Manager user is rejected
        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            recovery.retry_queue("LIQ-2026-00001")
        frappe.set_user("Administrator")

    def test_invalid_queue_rejected(self):
        # Test that non-existent queue throws error
        with self.assertRaises(frappe.ValidationError):
            recovery.retry_queue("NON_EXISTENT_QUEUE_99999")

    def test_customer360_blocked_when_normalize_fails(self):
        test_lead_id = f"997{int(time.time())}123"
        queue = frappe.get_doc({
            "doctype": "Lead Intake Queue",
            "source_lead_id": test_lead_id,
            "status": "Failed"
        }).insert(ignore_permissions=True)

        pipeline_engine.ensure_stage_ledger(queue.name)
        frappe.db.set_value("Lead Intake Stage", f"{queue.name}:GRAPH_DOWNLOAD", {"state": "FAILED"})
        frappe.db.set_value("Lead Intake Stage", f"{queue.name}:NORMALIZE", {"state": "FAILED"})

        pipeline_engine.rollup_queue(queue.name)
        c360_stage = pipeline_engine._stage_row(queue.name, "CUSTOMER360")
        self.assertEqual(c360_stage.state, "BLOCKED", "CUSTOMER360 stage must remain BLOCKED when NORMALIZE is FAILED")
        frappe.db.rollback()

    def test_pipeline_idempotency_and_evidence_merge(self):
        test_lead_id = f"999{int(time.time())}123"
        # Create a test queue with webhook context
        event = frappe.get_doc({
            "doctype": "Meta Webhook Event",
            "provider": "Meta",
            "event_type": "leadgen",
            "raw_json": json.dumps({"leadgen_id": test_lead_id, "page_id": "504890496038695", "form_id": "1744195093445660"})
        }).insert(ignore_permissions=True)

        queue = frappe.get_doc({
            "doctype": "Lead Intake Queue",
            "meta_webhook_event": event.name,
            "source_lead_id": test_lead_id,
            "page_id": "504890496038695",
            "form_id": "1744195093445660",
            "status": "Fetching Meta Lead"
        }).insert(ignore_permissions=True)

        pipeline_engine.ensure_stage_ledger(queue.name)

        # Mock graph payload
        mock_payload = {
            "id": test_lead_id,
            "created_time": "2026-07-08T19:44:00+0000",
            "form_id": "1744195093445660",
            "field_data": [
                {"name": "full_name", "values": ["John Doe"]},
                {"name": "phone_number", "values": ["+1234567890"]},
                {"name": "email", "values": ["john@example.com"]}
            ]
        }

        # Set mock graph payload directly to simulate successful GRAPH_DOWNLOAD
        frappe.db.set_value("Lead Intake Queue", queue.name, {
            "graph_payload": json.dumps(mock_payload),
            "graph_payload_hash": "test_hash"
        })
        frappe.db.set_value("Lead Intake Stage", f"{queue.name}:GRAPH_DOWNLOAD", {"state": "COMPLETED"})

        # Run process_queue
        res1 = intake_processor.process_queue(queue.name)
        self.assertTrue(res1.get("ok"), f"Pipeline execution failed: {res1}")

        q_after = frappe.get_doc("Lead Intake Queue", queue.name)
        self.assertEqual(q_after.page_id, "504890496038695", "page_id must be preserved from queue context")
        self.assertIsNotNone(q_after.matched_customer)
        self.assertIsNotNone(q_after.matched_lead)

        cust_id = q_after.matched_customer
        lead_id = q_after.matched_lead

        # Re-run process_queue to test idempotency
        res2 = intake_processor.process_queue(queue.name)
        q_after2 = frappe.get_doc("Lead Intake Queue", queue.name)

        self.assertEqual(q_after2.matched_customer, cust_id, "Idempotent run must not create a new Customer")
        self.assertEqual(q_after2.matched_lead, lead_id, "Idempotent run must not create a new CRM Lead")

        # Cleanup
        frappe.db.rollback()

    def test_classification_blocked_when_normalize_is_skipped(self):
        test_lead_id = f"996{int(time.time())}123"
        queue = frappe.get_doc({
            "doctype": "Lead Intake Queue",
            "source_lead_id": test_lead_id,
            "status": "Failed"
        }).insert(ignore_permissions=True)

        pipeline_engine.ensure_stage_ledger(queue.name)
        frappe.db.set_value("Lead Intake Stage", f"{queue.name}:NORMALIZE", {"state": "SKIPPED"})

        pipeline_engine.rollup_queue(queue.name)
        class_stage = pipeline_engine._stage_row(queue.name, "CLASSIFICATION")
        self.assertEqual(class_stage.state, "BLOCKED", "CLASSIFICATION stage must remain BLOCKED when NORMALIZE is SKIPPED")
        frappe.db.rollback()
