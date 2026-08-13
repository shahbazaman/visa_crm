import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch
from visa_crm.api import intake_processor
from visa_crm.api.pipeline_engine import retry_stage, run_stage
from visa_crm.patches.add_communication_event_pipeline_fields import execute as execute_migration

class TestCommunicationEventIdempotency(FrappeTestCase):
    def setUp(self):
        suffix = frappe.generate_hash(length=10)
        self.source = f"158403067{suffix[:7]}"
        self.phone = f"+9715{''.join(str(ord(c)%10) for c in suffix)[:8]}"
        self.email = f"comm.{suffix}@example.com"
        self.graph = {
            "id": self.source,
            "field_data": [
                {"name": "full_name", "values": [f"Comm Test Lead {suffix}"]},
                {"name": "phone", "values": [self.phone]},
                {"name": "email", "values": [self.email]},
                {"name": "visa_type", "values": ["Tourist"]}
            ],
            "form_id": "FORM-COMM-TEST",
            "campaign_id": "CAM-COMM-TEST",
            "campaign_name": "Meta Campaign Test"
        }
        doc = frappe.new_doc("Lead Intake Queue")
        doc.update({
            "status": "Lead Received",
            "source_lead_id": self.source,
            "event_type": "leadgen",
            "raw_payload": frappe.as_json({"change": {"field": "leadgen"}, "value": {"leadgen_id": self.source}})
        })
        doc.insert(ignore_permissions=True)
        self.queue = doc.name
        frappe.db.commit()

    def tearDown(self):
        queue = frappe.get_doc("Lead Intake Queue", self.queue)
        lead = queue.get("matched_lead")
        customer = queue.get("matched_customer")
        for doctype, filters in (
            ("Lead Intake AI Job", {"queue": self.queue}),
            ("Lead Assignment", {"lead_intake_queue": self.queue}),
            ("ToDo", {"meta_intake_key": f"followup:{self.queue}"}),
            ("Communication Event", {"event_id": f"meta:lead:{self.source}"}),
            ("Communication Event", {"facebook_lead_id": self.source}),
            ("Visa Application", {"meta_intake_key": f"visa:{self.queue}"}),
            ("Customer Identity", {"customer": customer}),
            ("CRM Lead", {"name": lead}),
            ("Customer", {"name": customer}),
            ("Lead Intake Stage", {"queue": self.queue}),
            ("Lead Intake Queue", {"name": self.queue})
        ):
            if frappe.db.exists("DocType", doctype):
                frappe.db.delete(doctype, filters)
        frappe.db.commit()

    def test_a_first_creation(self):
        employee = frappe.get_all("Employee", pluck="name", limit=1)[0]
        with patch("visa_crm.api.pipeline_stage_services.fetch_lead", return_value=self.graph), \
             patch("visa_crm.api.pipeline_stage_services.assign_lead", return_value=employee), \
             patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"):
            intake_processor.process_queue(self.queue, stage_budget=10)

        comm_event = frappe.db.get_value("Communication Event", {"event_id": f"meta:lead:{self.source}"}, ["name", "facebook_lead_id", "source_channel"], as_dict=True)
        self.assertIsNotNone(comm_event, "Communication Event must be findable by event_id")
        self.assertEqual(comm_event.facebook_lead_id, self.source)
        self.assertEqual(comm_event.source_channel, "Meta Lead Ads")

    def test_b_retry_does_not_duplicate(self):
        employee = frappe.get_all("Employee", pluck="name", limit=1)[0]
        with patch("visa_crm.api.pipeline_stage_services.fetch_lead", return_value=self.graph), \
             patch("visa_crm.api.pipeline_stage_services.assign_lead", return_value=employee), \
             patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"):
            res1 = intake_processor.process_queue(self.queue, stage_budget=10)
            self.assertTrue(retry_stage(self.queue, "COMMUNICATION_EVENT", force=True))
            res2 = intake_processor.process_queue(self.queue, stage_budget=10)

        events = frappe.get_all("Communication Event", filters={"event_id": f"meta:lead:{self.source}"}, pluck="name")
        self.assertEqual(len(events), 1, f"Should be exactly 1 Communication Event, got: {events}")
        self.assertEqual(res1["communication_event"], res2["communication_event"])

    def test_c_concurrent_workers(self):
        from visa_crm.api.pipeline_stage_services import communication_event
        from frappe.model.document import Document
        employee = frappe.get_all("Employee", pluck="name", limit=1)[0]
        with patch("visa_crm.api.pipeline_stage_services.fetch_lead", return_value=self.graph), \
             patch("visa_crm.api.pipeline_stage_services.assign_lead", return_value=employee), \
             patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"):
            intake_processor.process_queue(self.queue, stage_budget=8)  # Stop before COMMUNICATION_EVENT

        with patch.object(Document, "insert", side_effect=frappe.DuplicateEntryError("Communication Event", "dup", None)):
            res = communication_event(self.queue)
            self.assertIsNotNone(res["communication_event"])

    def test_d_migration_twice(self):
        execute_migration()
        execute_migration()
        cols = [c["Field"] for c in frappe.db.sql("SHOW COLUMNS FROM `tabCommunication Event`", as_dict=True)]
        self.assertIn("event_id", cols)
        self.assertIn("meta_attribution_json", cols)
        indexes = frappe.db.sql("SHOW INDEX FROM `tabCommunication Event` WHERE Column_name = 'event_id' AND Non_unique = 0", as_dict=True)
        self.assertTrue(len(indexes) > 0, "Unique index on event_id must exist in MariaDB")

    def test_f_missing_source_id_fails_loudly(self):
        from visa_crm.api.pipeline_stage_services import communication_event
        invalid_queue = frappe.new_doc("Lead Intake Queue")
        invalid_queue.status = "Lead Received"
        invalid_queue.raw_payload = "{}"
        invalid_queue.insert(ignore_permissions=True)

        with self.assertRaises(ValueError):
            communication_event(invalid_queue.name)

        frappe.db.delete("Lead Intake Queue", {"name": invalid_queue.name})

    def test_g_graph_failure_preserves_durable_queue(self):
        from visa_crm.api.meta_graph import MetaGraphError
        err = MetaGraphError("Graph API Timeout", status_code=500)
        with patch("visa_crm.api.pipeline_stage_services.fetch_lead", side_effect=err):
            intake_processor.process_queue(self.queue, stage_budget=2)
        qdoc = frappe.get_doc("Lead Intake Queue", self.queue)
        self.assertEqual(qdoc.source_lead_id, self.source)
        self.assertTrue(frappe.db.exists("Lead Intake Queue", self.queue))

    def test_h_worker_interruption_resumes_cleanly(self):
        employee = frappe.get_all("Employee", pluck="name", limit=1)[0]
        with patch("visa_crm.api.pipeline_stage_services.fetch_lead", return_value=self.graph), \
             patch("visa_crm.api.pipeline_stage_services.assign_lead", return_value=employee), \
             patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"):
            # Simulate worker death after NORMALIZE
            intake_processor.process_queue(self.queue, stage_budget=3)
            # Restart worker
            res = intake_processor.process_queue(self.queue, stage_budget=10)

        events = frappe.get_all("Communication Event", filters={"event_id": f"meta:lead:{self.source}"}, pluck="name")
        self.assertEqual(len(events), 1)
