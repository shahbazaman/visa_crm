"""
New simulated Meta lead end-to-end integration test.

Verifies that a unique fake Meta lead ID travels through the full pipeline:
  Meta webhook → Lead Intake Queue → Graph → Normalize → CRM Lead → Customer
  → Visa Application → Communication Event → Follow-up → Counselor → AI Queue

Run with:
  bench --site local.test run-tests --module visa_crm.tests.test_new_meta_lead_simulation
"""
from unittest.mock import patch
import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api import intake_processor
from visa_crm.api.meta_webhook import _insert_queue, _lead_source


class TestNewMetaLeadSimulation(FrappeTestCase):
    """
    Tests a brand-new simulated Meta lead end-to-end without reusing any previous test record.
    Uses a unique TEST-META-LEAD-<hash> ID that will never collide with real Meta leads.
    """

    def _unique_test_id(self):
        return f"TEST-META-LEAD-{frappe.generate_hash(length=12)}"

    def _build_graph_payload(self, leadgen_id, suffix):
        return {
            "id": leadgen_id,
            "created_time": "2026-08-01T09:00:00+0000",
            "field_data": [
                {"name": "full_name", "values": [f"Simulated Lead {suffix}"]},
                {"name": "phone", "values": [f"+97155{''.join(str(ord(c) % 10) for c in suffix)[:7]}"]},
                {"name": "email", "values": [f"sim.{suffix}@test-meta.example.com"]},
                {"name": "visa_type", "values": ["Business"]},
                {"name": "destination", "values": ["UAE"]},
            ],
            "form_id": "TEST-FORM-001",
            "campaign_name": "Test Campaign",
            "campaign_id": "TEST-CAM-001",
            "adset_name": "Test Adset",
            "adset_id": "TEST-SET-001",
            "ad_name": "Test Ad",
            "ad_id": "TEST-AD-001",
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Test 1: Webhook inserts queue record
    # ─────────────────────────────────────────────────────────────────────────
    def test_webhook_creates_lead_intake_queue(self):
        """Simulated Meta webhook must create a Lead Intake Queue record."""
        leadgen_id = self._unique_test_id()
        item = {
            "event_type": "leadgen",
            "source_lead_id": leadgen_id,
            "leadgen_id": leadgen_id,
            "page_id": "PAGE-SIM-001",
            "form_id": "FORM-SIM-001",
        }
        queue_name, created = _insert_queue(item, event_log=None)
        frappe.db.commit()

        self.assertTrue(created, "Webhook must create a new queue record for a new leadgen_id")
        self.assertTrue(frappe.db.exists("Lead Intake Queue", queue_name))

        # Duplicate: must NOT create a second record
        queue_name2, created2 = _insert_queue(item, event_log=None)
        frappe.db.commit()
        self.assertFalse(created2, "Duplicate webhook must not create a second queue record")
        self.assertEqual(queue_name, queue_name2)

        # Verify count in DB
        count = frappe.db.count("Lead Intake Queue", {"source_lead_id": leadgen_id})
        self.assertEqual(count, 1, "Exactly 1 Lead Intake Queue must exist for this leadgen_id")

    # ─────────────────────────────────────────────────────────────────────────
    # Test 2: Full pipeline creates all downstream records
    # ─────────────────────────────────────────────────────────────────────────
    def test_new_simulated_meta_lead_full_pipeline(self):
        """
        A unique simulated Meta lead ID must travel through the full pipeline and
        produce: CRM Lead, Customer, Visa Application, Communication Event,
        Follow-up ToDo, Counselor Assignment, AI Job queue entry.
        """
        suffix = frappe.generate_hash(length=12)
        leadgen_id = f"TEST-META-LEAD-{suffix}"
        phone = f"+97155{''.join(str(ord(c) % 10) for c in suffix)[:7]}"
        email = f"sim.{suffix}@test-meta.example.com"
        graph = self._build_graph_payload(leadgen_id, suffix)

        # Create the queue entry directly (as webhook would)
        queue = frappe.new_doc("Lead Intake Queue")
        queue.status = "Lead Received"
        queue.source_lead_id = leadgen_id
        queue.event_type = "leadgen"
        queue.page_id = "PAGE-SIM-TEST"
        queue.form_id = "FORM-SIM-TEST"
        queue.raw_payload = frappe.as_json({
            "value": {"leadgen_id": leadgen_id, "page_id": "PAGE-SIM-TEST", "form_id": "FORM-SIM-TEST"},
            "change": {"field": "leadgen"}
        })
        queue.insert(ignore_permissions=True)
        frappe.db.commit()

        # Run the pipeline with mocks for external dependencies:
        # - fetch_lead: mocked to return our canned graph payload (no real HTTP)
        # - get_meta_settings: mocked to return empty settings (no real API key needed)
        # - frappe.enqueue: mocked to prevent real AI job dispatch
        # - _is_working: mocked to return True (time-invariant assignment)
        with (
            patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()),
            patch("visa_crm.api.pipeline_stage_services.fetch_lead", return_value=graph),
            patch("visa_crm.api.pipeline_stage_services.frappe.enqueue") as mock_enqueue,
            patch("visa_crm.api.lead_assignment._is_working", return_value=True),
        ):
            result = intake_processor.process_queue(queue.name)
            queue.reload()

        # ── Queue-level assertions ──────────────────────────────────────────
        self.assertTrue(result["ok"], f"Pipeline must succeed. Result: {result}")
        self.assertEqual(
            queue.status, "Processed",
            f"Queue status must be 'Processed'. Got: '{queue.status}'. "
            f"orchestration_status='{queue.orchestration_status}' stage_summary="
            f"{queue.get('stage_summary_json','')[:400]}"
        )
        self.assertEqual(queue.orchestration_status, "COMPLETED")
        self.assertEqual(queue.source_lead_id, leadgen_id)

        # ── CRM Lead ────────────────────────────────────────────────────────
        self.assertTrue(queue.matched_lead, "CRM Lead must be created")
        lead = frappe.get_doc("CRM Lead", queue.matched_lead)
        self.assertEqual(lead.facebook_lead_id, leadgen_id)
        self.assertEqual(lead.mobile_no, phone)
        self.assertEqual(lead.email, email)
        self.assertIsNotNone(lead.customer360, "CRM Lead must be linked to a Customer")

        # ── Customer ────────────────────────────────────────────────────────
        self.assertTrue(queue.matched_customer, "Customer must be created")
        customer = frappe.get_doc("Customer", queue.matched_customer)
        self.assertEqual(customer.crm_lead, lead.name)

        # ── Visa Application ────────────────────────────────────────────────
        self.assertTrue(queue.visa_application, "Visa Application must be created")
        visa = frappe.get_doc("Visa Application", queue.visa_application)
        self.assertEqual(visa.lead, lead.name)
        self.assertEqual(visa.customer, customer.name)

        # ── Communication Event ─────────────────────────────────────────────
        self.assertTrue(queue.communication_event, "Communication Event must be created")
        event = frappe.get_doc("Communication Event", queue.communication_event)
        self.assertEqual(event.lead, lead.name)
        self.assertEqual(event.customer, customer.name)
        self.assertEqual(event.visa_application, visa.name)
        self.assertEqual(event.lead_intake_queue, queue.name)

        # ── Follow-up ───────────────────────────────────────────────────────
        self.assertTrue(queue.followup_reference, "Follow-up ToDo must be created")

        # ── Counselor Assignment ────────────────────────────────────────────
        self.assertTrue(queue.assigned_employee, "Counselor must be assigned")
        self.assertTrue(
            frappe.db.exists("Lead Assignment", {"lead": lead.name, "assigned_to": queue.assigned_employee}),
            "Lead Assignment record must be created"
        )

        # ── AI Dispatch ─────────────────────────────────────────────────────
        self.assertEqual(queue.ai_status, "Queued", "AI status must be Queued after AI_DISPATCH stage")
        mock_enqueue.assert_called_once()

        # ── Verify lead is findable by facebook_lead_id ─────────────────────
        found = frappe.get_list(
            "CRM Lead",
            filters={"facebook_lead_id": leadgen_id},
            fields=["name", "lead_name", "facebook_lead_id"],
        )
        self.assertEqual(len(found), 1, "Exactly one CRM Lead must exist for this facebook_lead_id")
        self.assertEqual(found[0].facebook_lead_id, leadgen_id)

        # ── All pipeline stages in COMPLETED state ──────────────────────────
        states = dict(frappe.get_all(
            "Lead Intake Stage",
            filters={"queue": queue.name},
            fields=["stage", "state"],
            as_list=True,
        ))
        mandatory_stages = (
            "GRAPH_DOWNLOAD", "NORMALIZE", "CLASSIFICATION",
            "CUSTOMER360", "CRM_LEAD", "LEAD_WORKFLOW",
            "VISA_APPLICATION", "COMMUNICATION_EVENT",
            "FOLLOW_UP", "COUNSELOR_ASSIGNMENT", "AI_DISPATCH",
        )
        for stage in mandatory_stages:
            self.assertEqual(
                states.get(stage), "COMPLETED",
                f"Stage {stage} must be COMPLETED. Got: '{states.get(stage)}'"
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Test 3: Idempotency — re-running process_queue does not duplicate records
    # ─────────────────────────────────────────────────────────────────────────
    def test_duplicate_webhook_does_not_create_duplicate_crm_lead(self):
        """
        Running process_queue twice on an already-completed queue must not create
        a second CRM Lead.
        """
        suffix = frappe.generate_hash(length=12)
        leadgen_id = f"TEST-META-LEAD-{suffix}"
        graph = self._build_graph_payload(leadgen_id, suffix)

        queue = frappe.new_doc("Lead Intake Queue")
        queue.status = "Lead Received"
        queue.source_lead_id = leadgen_id
        queue.event_type = "leadgen"
        queue.raw_payload = frappe.as_json({
            "value": {"leadgen_id": leadgen_id}, "change": {"field": "leadgen"}
        })
        queue.insert(ignore_permissions=True)
        frappe.db.commit()

        with (
            patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()),
            patch("visa_crm.api.pipeline_stage_services.fetch_lead", return_value=graph),
            patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"),
            patch("visa_crm.api.lead_assignment._is_working", return_value=True),
        ):
            intake_processor.process_queue(queue.name)
            # Run again — idempotency check
            intake_processor.process_queue(queue.name)

        count = frappe.db.count("CRM Lead", {"facebook_lead_id": leadgen_id})
        self.assertEqual(count, 1, "Re-processing must not create a duplicate CRM Lead")

    # ─────────────────────────────────────────────────────────────────────────
    # Test 4: Graph failure does not delete the queue
    # ─────────────────────────────────────────────────────────────────────────
    def test_graph_failure_does_not_delete_queue(self):
        """
        If the GRAPH_DOWNLOAD stage fails (network error), the Lead Intake Queue
        record must still exist and be in a retryable state.
        """
        leadgen_id = self._unique_test_id()

        queue = frappe.new_doc("Lead Intake Queue")
        queue.status = "Lead Received"
        queue.source_lead_id = leadgen_id
        queue.event_type = "leadgen"
        queue.raw_payload = frappe.as_json({
            "value": {"leadgen_id": leadgen_id}, "change": {"field": "leadgen"}
        })
        queue.insert(ignore_permissions=True)
        frappe.db.commit()

        class FakeGraphError(Exception):
            pass

        with (
            patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()),
            patch("visa_crm.api.pipeline_stage_services.fetch_lead", side_effect=FakeGraphError("Network timeout")),
            patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"),
        ):
            intake_processor.process_queue(queue.name)

        # Queue must still exist
        self.assertTrue(
            frappe.db.exists("Lead Intake Queue", queue.name),
            "Lead Intake Queue must NOT be deleted on graph failure"
        )
        queue.reload()
        self.assertNotIn(
            queue.status, ("Processed", "Processed With Warnings"),
            "Queue must not be marked as Processed when graph download failed"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Test 5: AI failure does not delete mandatory records
    # ─────────────────────────────────────────────────────────────────────────
    def test_counselor_unavailable_does_not_delete_business_records(self):
        """
        If counselor assignment fails (no eligible counselor), the CRM Lead,
        Customer, Visa Application, and Communication Event must still exist.
        """
        suffix = frappe.generate_hash(length=12)
        leadgen_id = f"TEST-META-LEAD-{suffix}"
        graph = self._build_graph_payload(leadgen_id, suffix)

        queue = frappe.new_doc("Lead Intake Queue")
        queue.status = "Lead Received"
        queue.source_lead_id = leadgen_id
        queue.event_type = "leadgen"
        queue.raw_payload = frappe.as_json({
            "value": {"leadgen_id": leadgen_id}, "change": {"field": "leadgen"}
        })
        queue.insert(ignore_permissions=True)
        frappe.db.commit()

        # Do NOT mock _is_working — let counselor assignment fail naturally
        with (
            patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()),
            patch("visa_crm.api.pipeline_stage_services.fetch_lead", return_value=graph),
            patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"),
            patch("visa_crm.api.lead_assignment._is_working", return_value=False),  # force no counselor
        ):
            intake_processor.process_queue(queue.name)

        queue.reload()

        # All mandatory business records must exist even if counselor assignment failed
        self.assertTrue(queue.matched_lead, "CRM Lead must exist even when counselor is unavailable")
        self.assertTrue(queue.matched_customer, "Customer must exist even when counselor is unavailable")
        self.assertTrue(queue.visa_application, "Visa Application must exist even when counselor is unavailable")
        self.assertTrue(queue.communication_event, "Communication Event must exist even when counselor is unavailable")

        # Status should be Processed With Warnings (not failed)
        self.assertIn(
            queue.status,
            ["Processed With Warnings", "Processed"],
            f"Queue status must be Processed or Processed With Warnings when counselor unavailable. Got: {queue.status}"
        )
