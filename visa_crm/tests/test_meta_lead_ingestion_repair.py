from unittest.mock import patch
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime
from visa_crm.api import intake_processor, meta_graph, meta_webhook, pipeline_stage_services
from visa_crm.api.lead_permissions import crm_lead_query
from visa_crm.api.meta_graph import MetaGraphError, fetch_lead

class TestMetaLeadIngestionRepair(FrappeTestCase):
    def test_a_correct_leadgen_id_propagation(self):
        source_id = "1272720881498434"
        received_ids = []

        def fake_get(path, params):
            received_ids.append(path)
            return {
                "id": path,
                "created_time": "2026-08-11T10:00:00+0000",
                "field_data": [{"name": "full_name", "values": ["Propagation Test"]}],
                "form_id": "FORM-PROP",
            }

        with patch("visa_crm.api.meta_graph._get", side_effect=fake_get), patch("visa_crm.api.meta_graph._access_token", return_value="FAKE_TOKEN"):
            res = fetch_lead(source_id)

        self.assertEqual(len(received_ids), 1)
        self.assertEqual(received_ids[0], source_id)
        self.assertIsNotNone(res)

    def test_b_webhook_to_queue_mapping(self):
        leadgen_id = f"12727{frappe.generate_hash(length=8)}"
        payload = {
            "object": "page",
            "entry": [
                {
                    "id": "PAGE-MAPPING-TEST",
                    "changes": [
                        {
                            "field": "leadgen",
                            "value": {
                                "leadgen_id": leadgen_id,
                                "page_id": "PAGE-MAPPING-TEST",
                                "form_id": "FORM-MAPPING-TEST",
                            },
                        }
                    ],
                }
            ],
        }

        with patch("visa_crm.api.meta_webhook._valid_signature", return_value=True), patch("frappe.enqueue"):
            meta_webhook.replay_payload(payload)

        evt_name = frappe.db.get_value("Meta Webhook Event", {"leadgen_id": leadgen_id}, "name")
        self.assertTrue(evt_name)

        q_name = frappe.db.get_value("Lead Intake Queue", {"source_lead_id": leadgen_id}, "name")
        self.assertTrue(q_name)

        q_source_id = frappe.db.get_value("Lead Intake Queue", q_name, "source_lead_id")
        evt_lead_id = frappe.db.get_value("Meta Webhook Event", evt_name, "leadgen_id")
        self.assertEqual(evt_lead_id, q_source_id)

    def test_c_graph_success(self):
        leadgen_id = f"9900{frappe.generate_hash(length=8)}"
        queue = frappe.new_doc("Lead Intake Queue")
        queue.status = "Lead Received"
        queue.source_lead_id = leadgen_id
        queue.event_type = "leadgen"
        queue.page_id = "PAGE-C"
        queue.form_id = "FORM-C"
        queue.raw_payload = frappe.as_json({"value": {"leadgen_id": leadgen_id, "page_id": "PAGE-C", "form_id": "FORM-C"}})
        queue.insert(ignore_permissions=True)

        graph_response = {
            "id": leadgen_id,
            "created_time": "2026-08-11T12:00:00+0000",
            "field_data": [
                {"name": "full_name", "values": [f"Success Lead {leadgen_id}"]},
                {"name": "phone", "values": ["+971501112233"]},
                {"name": "email", "values": [f"success.{leadgen_id}@example.com"]},
            ],
            "form_id": "FORM-C",
        }

        with patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()), patch("visa_crm.api.pipeline_stage_services.fetch_lead", return_value=graph_response), patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"), patch("visa_crm.api.lead_assignment._is_working", return_value=True):
            res = intake_processor.process_queue(queue.name)

        queue.reload()
        self.assertTrue(res["ok"])
        states = dict(frappe.get_all("Lead Intake Stage", filters={"queue": queue.name}, fields=["stage", "state"], as_list=True))
        self.assertEqual(states["GRAPH_DOWNLOAD"], "COMPLETED")
        self.assertEqual(states["NORMALIZE"], "COMPLETED")
        self.assertEqual(states["CUSTOMER360"], "COMPLETED")
        self.assertEqual(states["CRM_LEAD"], "COMPLETED")
        self.assertTrue(frappe.db.exists("CRM Lead", {"facebook_lead_id": leadgen_id}))

    def test_d_graph_failure(self):
        leadgen_id = f"9900{frappe.generate_hash(length=8)}"
        queue = frappe.new_doc("Lead Intake Queue")
        queue.status = "Lead Received"
        queue.source_lead_id = leadgen_id
        queue.event_type = "leadgen"
        queue.page_id = "PAGE-D"
        queue.form_id = "FORM-D"
        queue.raw_payload = frappe.as_json({"value": {"leadgen_id": leadgen_id, "page_id": "PAGE-D", "form_id": "FORM-D"}})
        queue.insert(ignore_permissions=True)

        err = MetaGraphError(
            "Meta Graph API Permission Error (Unsupported get request. Object with ID 'None' does not exist): Page Access Token lacks 'leads_retrieval' permission",
            status_code=400,
        )

        with patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()), patch("visa_crm.api.pipeline_stage_services.fetch_lead", side_effect=err):
            res = intake_processor.process_queue(queue.name)

        queue.reload()
        states = dict(frappe.get_all("Lead Intake Stage", filters={"queue": queue.name}, fields=["stage", "state"], as_list=True))
        self.assertEqual(states["GRAPH_DOWNLOAD"], "FAILED")
        self.assertEqual(queue.source_lead_id, leadgen_id)

    def test_e_retry_pipeline_recovery(self):
        leadgen_id = f"9900{frappe.generate_hash(length=8)}"
        queue = frappe.new_doc("Lead Intake Queue")
        queue.status = "Lead Received"
        queue.source_lead_id = leadgen_id
        queue.event_type = "leadgen"
        queue.page_id = "PAGE-E"
        queue.form_id = "FORM-E"
        queue.raw_payload = frappe.as_json({"value": {"leadgen_id": leadgen_id, "page_id": "PAGE-E", "form_id": "FORM-E"}})
        queue.insert(ignore_permissions=True)

        err = MetaGraphError("Graph API Error #100", status_code=400)
        with patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()), patch("visa_crm.api.pipeline_stage_services.fetch_lead", side_effect=err):
            intake_processor.process_queue(queue.name)

        with patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()), patch("visa_crm.api.pipeline_stage_services.fetch_lead", side_effect=err), patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"), patch("visa_crm.api.lead_assignment._is_working", return_value=True):
            res = intake_processor.process_queue(queue.name)

        queue.reload()
        states = dict(frappe.get_all("Lead Intake Stage", filters={"queue": queue.name}, fields=["stage", "state"], as_list=True))
        self.assertEqual(states["GRAPH_DOWNLOAD"], "FAILED")
        self.assertEqual(states["NORMALIZE"], "COMPLETED")
        self.assertEqual(states["CUSTOMER360"], "COMPLETED")
        self.assertEqual(states["CRM_LEAD"], "COMPLETED")
        self.assertTrue(queue.matched_lead)
        self.assertTrue(queue.matched_customer)

    def test_f_duplicate_retry_idempotency(self):
        leadgen_id = f"9900{frappe.generate_hash(length=8)}"
        queue = frappe.new_doc("Lead Intake Queue")
        queue.status = "Lead Received"
        queue.source_lead_id = leadgen_id
        queue.event_type = "leadgen"
        queue.page_id = "PAGE-F"
        queue.form_id = "FORM-F"
        queue.raw_payload = frappe.as_json({"value": {"leadgen_id": leadgen_id, "page_id": "PAGE-F", "form_id": "FORM-F"}})
        queue.insert(ignore_permissions=True)

        graph_response = {
            "id": leadgen_id,
            "created_time": "2026-08-11T12:00:00+0000",
            "field_data": [{"name": "full_name", "values": [f"Idempotent Lead {leadgen_id}"]}],
            "form_id": "FORM-F",
        }

        with patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()), patch("visa_crm.api.pipeline_stage_services.fetch_lead", return_value=graph_response), patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"), patch("visa_crm.api.lead_assignment._is_working", return_value=True):
            intake_processor.process_queue(queue.name)
            intake_processor.process_queue(queue.name)

        lead_count = frappe.db.count("CRM Lead", {"facebook_lead_id": leadgen_id})
        self.assertEqual(lead_count, 1)

    def test_g_stale_retry_timestamp(self):
        leadgen_id = f"9900{frappe.generate_hash(length=8)}"
        now_dt = now_datetime()
        queue = frappe.new_doc("Lead Intake Queue")
        queue.status = "Lead Received"
        queue.source_lead_id = leadgen_id
        queue.event_type = "leadgen"
        queue.raw_payload = frappe.as_json({"value": {"leadgen_id": leadgen_id}})
        queue.insert(ignore_permissions=True)

        queue.reload()
        if queue.next_action_at:
            self.assertGreaterEqual(queue.next_action_at, queue.creation)

    def test_h_existing_queue_recovery(self):
        leadgen_id = f"9044{frappe.generate_hash(length=8)}"
        queue = frappe.new_doc("Lead Intake Queue")
        queue.status = "Failed"
        queue.orchestration_status = "FAILED"
        queue.current_stage = "GRAPH_DOWNLOAD"
        queue.source_lead_id = leadgen_id
        queue.event_type = "leadgen"
        queue.page_id = "504890496038695"
        queue.form_id = "2148691029027696"
        queue.raw_payload = frappe.as_json({
            "event_type": "leadgen",
            "entry_id": "504890496038695",
            "source_lead_id": leadgen_id,
            "leadgen_id": leadgen_id,
            "page_id": "504890496038695",
            "form_id": "2148691029027696",
        })
        queue.insert(ignore_permissions=True)

        err = MetaGraphError("Unsupported get request. Object with ID 'None' does not exist", status_code=400)
        with patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()), patch("visa_crm.api.pipeline_stage_services.fetch_lead", side_effect=err), patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"), patch("visa_crm.api.lead_assignment._is_working", return_value=True):
            res = intake_processor.process_queue(queue.name)

        queue.reload()
        self.assertTrue(queue.matched_lead)
        self.assertTrue(frappe.db.exists("CRM Lead", queue.matched_lead))

    def test_i_crm_visibility(self):
        leadgen_id = f"9900{frappe.generate_hash(length=8)}"
        queue = frappe.new_doc("Lead Intake Queue")
        queue.status = "Lead Received"
        queue.source_lead_id = leadgen_id
        queue.event_type = "leadgen"
        queue.raw_payload = frappe.as_json({"value": {"leadgen_id": leadgen_id}})
        queue.insert(ignore_permissions=True)

        graph_response = {
            "id": leadgen_id,
            "created_time": "2026-08-11T12:00:00+0000",
            "field_data": [{"name": "full_name", "values": [f"Visible Lead {leadgen_id}"]}],
        }

        with patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()), patch("visa_crm.api.pipeline_stage_services.fetch_lead", return_value=graph_response), patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"), patch("visa_crm.api.lead_assignment._is_working", return_value=True):
            intake_processor.process_queue(queue.name)

        queue.reload()
        lead_name = queue.matched_lead
        self.assertTrue(lead_name)

        cond = crm_lead_query("Administrator")
        self.assertEqual(cond, "")

        leads = frappe.get_all("CRM Lead", filters={"name": lead_name})
        self.assertEqual(len(leads), 1)
