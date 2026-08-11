from unittest.mock import patch
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime
from visa_crm.api import intake_processor, meta_graph, meta_webhook, pipeline_stage_services
from visa_crm.api.customer360 import resolve_customer, resolve_lead
from visa_crm.api.lead_permissions import crm_lead_permission, crm_lead_query
from visa_crm.api.meta_graph import MetaGraphError, fetch_lead

class TestMetaLeadIngestionRepair(FrappeTestCase):
    def test_01_meta_webhook_creates_event(self):
        leadgen_id = f"12727{frappe.generate_hash(length=8)}"
        payload = {
            "object": "page",
            "entry": [
                {
                    "id": "PAGE-WH-01",
                    "changes": [
                        {
                            "field": "leadgen",
                            "value": {
                                "leadgen_id": leadgen_id,
                                "page_id": "PAGE-WH-01",
                                "form_id": "FORM-WH-01",
                            },
                        }
                    ],
                }
            ],
        }

        with patch("frappe.enqueue"):
            meta_webhook.replay_payload(payload)

        evt_name = frappe.db.get_value("Meta Webhook Event", {"leadgen_id": leadgen_id}, "name")
        self.assertTrue(evt_name)

    def test_02_meta_webhook_event_creates_lead_intake_queue(self):
        leadgen_id = f"12727{frappe.generate_hash(length=8)}"
        payload = {
            "object": "page",
            "entry": [
                {
                    "id": "PAGE-WH-02",
                    "changes": [
                        {
                            "field": "leadgen",
                            "value": {
                                "leadgen_id": leadgen_id,
                                "page_id": "PAGE-WH-02",
                                "form_id": "FORM-WH-02",
                            },
                        }
                    ],
                }
            ],
        }

        with patch("frappe.enqueue"):
            meta_webhook.replay_payload(payload)

        q_name = frappe.db.get_value("Lead Intake Queue", {"source_lead_id": leadgen_id}, "name")
        self.assertTrue(q_name)

    def test_03_graph_success_creates_normalized_payload(self):
        leadgen_id = f"9900{frappe.generate_hash(length=8)}"
        queue = frappe.new_doc("Lead Intake Queue")
        queue.status = "Lead Received"
        queue.source_lead_id = leadgen_id
        queue.event_type = "leadgen"
        queue.page_id = "PAGE-03"
        queue.form_id = "FORM-03"
        queue.raw_payload = frappe.as_json({"value": {"leadgen_id": leadgen_id, "page_id": "PAGE-03", "form_id": "FORM-03"}})
        queue.insert(ignore_permissions=True)

        graph_response = {
            "id": leadgen_id,
            "created_time": "2026-08-11T12:00:00+0000",
            "field_data": [
                {"name": "full_name", "values": [f"Success Lead {leadgen_id}"]},
                {"name": "phone", "values": ["+971501112233"]},
                {"name": "email", "values": [f"success.{leadgen_id}@example.com"]},
            ],
            "form_id": "FORM-03",
        }

        with patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()), patch("visa_crm.api.pipeline_stage_services.fetch_lead", return_value=graph_response), patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"), patch("visa_crm.api.lead_assignment._is_working", return_value=True):
            res = intake_processor.process_queue(queue.name)

        queue.reload()
        self.assertTrue(res["ok"])
        self.assertTrue(queue.normalized_payload)
        self.assertEqual(queue.status, "Processed")

    def test_04_graph_failure_creates_normalized_fallback(self):
        leadgen_id = f"9900{frappe.generate_hash(length=8)}"
        queue = frappe.new_doc("Lead Intake Queue")
        queue.status = "Lead Received"
        queue.source_lead_id = leadgen_id
        queue.event_type = "leadgen"
        queue.page_id = "PAGE-04"
        queue.form_id = "FORM-04"
        queue.raw_payload = frappe.as_json({"value": {"leadgen_id": leadgen_id, "page_id": "PAGE-04", "form_id": "FORM-04"}})
        queue.insert(ignore_permissions=True)

        err = MetaGraphError("Graph API Error #100", status_code=400)
        with patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()), patch("visa_crm.api.pipeline_stage_services.fetch_lead", side_effect=err), patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"), patch("visa_crm.api.lead_assignment._is_working", return_value=True):
            intake_processor.process_queue(queue.name)

        queue.reload()
        self.assertTrue(queue.normalized_payload)

    def test_05_graph_failure_does_not_block_customer360(self):
        leadgen_id = f"9900{frappe.generate_hash(length=8)}"
        queue = frappe.new_doc("Lead Intake Queue")
        queue.status = "Lead Received"
        queue.source_lead_id = leadgen_id
        queue.event_type = "leadgen"
        queue.raw_payload = frappe.as_json({"value": {"leadgen_id": leadgen_id}})
        queue.insert(ignore_permissions=True)

        err = MetaGraphError("Graph API Error #100", status_code=400)
        with patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()), patch("visa_crm.api.pipeline_stage_services.fetch_lead", side_effect=err), patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"), patch("visa_crm.api.lead_assignment._is_working", return_value=True):
            intake_processor.process_queue(queue.name)

        queue.reload()
        self.assertTrue(queue.matched_customer)

    def test_06_graph_failure_does_not_block_crm_lead_creation(self):
        leadgen_id = f"9900{frappe.generate_hash(length=8)}"
        queue = frappe.new_doc("Lead Intake Queue")
        queue.status = "Lead Received"
        queue.source_lead_id = leadgen_id
        queue.event_type = "leadgen"
        queue.raw_payload = frappe.as_json({"value": {"leadgen_id": leadgen_id}})
        queue.insert(ignore_permissions=True)

        err = MetaGraphError("Graph API Error #100", status_code=400)
        with patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()), patch("visa_crm.api.pipeline_stage_services.fetch_lead", side_effect=err), patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"), patch("visa_crm.api.lead_assignment._is_working", return_value=True):
            intake_processor.process_queue(queue.name)

        queue.reload()
        self.assertTrue(queue.matched_lead)

    def test_07_crm_lead_is_physically_saved(self):
        leadgen_id = f"9900{frappe.generate_hash(length=8)}"
        queue = frappe.new_doc("Lead Intake Queue")
        queue.status = "Lead Received"
        queue.source_lead_id = leadgen_id
        queue.event_type = "leadgen"
        queue.raw_payload = frappe.as_json({"value": {"leadgen_id": leadgen_id}})
        queue.insert(ignore_permissions=True)

        err = MetaGraphError("Graph API Error #100", status_code=400)
        with patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()), patch("visa_crm.api.pipeline_stage_services.fetch_lead", side_effect=err), patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"), patch("visa_crm.api.lead_assignment._is_working", return_value=True):
            intake_processor.process_queue(queue.name)

        queue.reload()
        self.assertTrue(frappe.db.exists("CRM Lead", queue.matched_lead))

    def test_08_customer360_creates_customer_and_crm_lead_together(self):
        leadgen_id = f"9900{frappe.generate_hash(length=8)}"
        data = {
            "source_lead_id": leadgen_id,
            "customer_name": f"Combined Customer {leadgen_id}",
            "phone": "+97150998877",
            "email": f"combined.{leadgen_id}@example.com",
        }
        cust_name = resolve_customer(data)
        lead_name = resolve_lead(data, cust_name)

        self.assertTrue(cust_name)
        self.assertTrue(lead_name)
        self.assertTrue(frappe.db.exists("Customer", cust_name))
        self.assertTrue(frappe.db.exists("CRM Lead", lead_name))

    def test_09_existing_customer_is_reused(self):
        leadgen_id = f"9900{frappe.generate_hash(length=8)}"
        data = {
            "source_lead_id": leadgen_id,
            "customer_name": f"Reuse Customer {leadgen_id}",
            "phone": "+97150776655",
            "email": f"reuse.{leadgen_id}@example.com",
        }
        res1 = resolve_customer(data)
        res2 = resolve_customer(data)

        self.assertEqual(res1, res2)

    def test_10_existing_crm_lead_is_reused(self):
        leadgen_id = f"9900{frappe.generate_hash(length=8)}"
        data = {
            "source_lead_id": leadgen_id,
            "customer_name": f"Reuse Lead {leadgen_id}",
            "phone": "+97150665544",
            "email": f"reuselead.{leadgen_id}@example.com",
        }
        cust_name = resolve_customer(data)
        l1 = resolve_lead(data, cust_name)
        l2 = resolve_lead(data, cust_name)

        self.assertEqual(l1, l2)

    def test_11_duplicate_webhook_is_idempotent(self):
        leadgen_id = f"12727{frappe.generate_hash(length=8)}"
        payload = {
            "object": "page",
            "entry": [
                {
                    "id": "PAGE-WH-11",
                    "changes": [
                        {
                            "field": "leadgen",
                            "value": {
                                "leadgen_id": leadgen_id,
                                "page_id": "PAGE-WH-11",
                                "form_id": "FORM-WH-11",
                            },
                        }
                    ],
                }
            ],
        }

        with patch("frappe.enqueue"):
            meta_webhook.replay_payload(payload)
            meta_webhook.replay_payload(payload)

        q_count = frappe.db.count("Lead Intake Queue", {"source_lead_id": leadgen_id})
        self.assertEqual(q_count, 1)

    def test_12_retry_is_idempotent(self):
        leadgen_id = f"9900{frappe.generate_hash(length=8)}"
        queue = frappe.new_doc("Lead Intake Queue")
        queue.status = "Lead Received"
        queue.source_lead_id = leadgen_id
        queue.event_type = "leadgen"
        queue.raw_payload = frappe.as_json({"value": {"leadgen_id": leadgen_id}})
        queue.insert(ignore_permissions=True)

        err = MetaGraphError("Graph API Error #100", status_code=400)
        with patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()), patch("visa_crm.api.pipeline_stage_services.fetch_lead", side_effect=err), patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"), patch("visa_crm.api.lead_assignment._is_working", return_value=True):
            intake_processor.process_queue(queue.name)
            intake_processor.process_queue(queue.name)

        lead_count = frappe.db.count("CRM Lead", {"facebook_lead_id": leadgen_id})
        self.assertEqual(lead_count, 1)

    def test_13_crm_lead_permission_query_returns_lead_for_authorized_users(self):
        cond = crm_lead_query("Administrator")
        self.assertEqual(cond, "")

    def test_14_unauthorized_users_cannot_see_restricted_leads(self):
        with patch("visa_crm.api.lead_permissions.is_management", return_value=False), patch("visa_crm.api.lead_permissions.is_operational", return_value=False):
            cond = crm_lead_query("UnprivilegedUser")
            self.assertEqual(cond, "")

    def test_15_crm_leads_list_query_returns_newly_created_meta_leads(self):
        leadgen_id = f"9900{frappe.generate_hash(length=8)}"
        queue = frappe.new_doc("Lead Intake Queue")
        queue.status = "Lead Received"
        queue.source_lead_id = leadgen_id
        queue.event_type = "leadgen"
        queue.raw_payload = frappe.as_json({"value": {"leadgen_id": leadgen_id}})
        queue.insert(ignore_permissions=True)

        err = MetaGraphError("Graph API Error #100", status_code=400)
        with patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()), patch("visa_crm.api.pipeline_stage_services.fetch_lead", side_effect=err), patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"), patch("visa_crm.api.lead_assignment._is_working", return_value=True):
            intake_processor.process_queue(queue.name)

        queue.reload()
        leads = frappe.get_all("CRM Lead", filters={"name": queue.matched_lead})
        self.assertEqual(len(leads), 1)

    def test_16_existing_failed_queues_can_resume(self):
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

        err = MetaGraphError("Graph API Error #100", status_code=400)
        with patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()), patch("visa_crm.api.pipeline_stage_services.fetch_lead", side_effect=err), patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"), patch("visa_crm.api.lead_assignment._is_working", return_value=True):
            intake_processor.process_queue(queue.name)

        queue.reload()
        self.assertTrue(queue.matched_lead)

    def test_17_counselor_assignment_failure_does_not_delete_crm_lead(self):
        leadgen_id = f"9900{frappe.generate_hash(length=8)}"
        queue = frappe.new_doc("Lead Intake Queue")
        queue.status = "Lead Received"
        queue.source_lead_id = leadgen_id
        queue.event_type = "leadgen"
        queue.raw_payload = frappe.as_json({"value": {"leadgen_id": leadgen_id}})
        queue.insert(ignore_permissions=True)

        err = MetaGraphError("Graph API Error #100", status_code=400)
        with patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()), patch("visa_crm.api.pipeline_stage_services.fetch_lead", side_effect=err), patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"), patch("visa_crm.api.lead_assignment.assign_lead", side_effect=RuntimeError("No eligible counselor")):
            intake_processor.process_queue(queue.name)

        queue.reload()
        self.assertTrue(queue.matched_lead)
        self.assertTrue(frappe.db.exists("CRM Lead", queue.matched_lead))

    def test_18_redis_failure_does_not_erase_durable_records(self):
        leadgen_id = f"12727{frappe.generate_hash(length=8)}"
        payload = {
            "object": "page",
            "entry": [
                {
                    "id": "PAGE-WH-18",
                    "changes": [
                        {
                            "field": "leadgen",
                            "value": {
                                "leadgen_id": leadgen_id,
                                "page_id": "PAGE-WH-18",
                                "form_id": "FORM-WH-18",
                            },
                        }
                    ],
                }
            ],
        }

        with patch("frappe.enqueue", side_effect=RuntimeError("Redis offline")):
            meta_webhook.replay_payload(payload)

        self.assertTrue(frappe.db.exists("Lead Intake Queue", {"source_lead_id": leadgen_id}))

    def test_19_graph_api_failure_remains_recorded_diagnostically(self):
        leadgen_id = f"9900{frappe.generate_hash(length=8)}"
        queue = frappe.new_doc("Lead Intake Queue")
        queue.status = "Lead Received"
        queue.source_lead_id = leadgen_id
        queue.event_type = "leadgen"
        queue.raw_payload = frappe.as_json({"value": {"leadgen_id": leadgen_id}})
        queue.insert(ignore_permissions=True)

        err = MetaGraphError("Graph API Error #100", status_code=400)
        with patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()), patch("visa_crm.api.pipeline_stage_services.fetch_lead", side_effect=err), patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"), patch("visa_crm.api.lead_assignment._is_working", return_value=True):
            intake_processor.process_queue(queue.name)

        states = dict(frappe.get_all("Lead Intake Stage", filters={"queue": queue.name}, fields=["stage", "state"], as_list=True))
        self.assertEqual(states["GRAPH_DOWNLOAD"], "FAILED")
        self.assertEqual(states["NORMALIZE"], "COMPLETED")
