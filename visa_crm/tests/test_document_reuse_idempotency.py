import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api import intake_processor
from visa_crm.api.meta_webhook import replay_payload
from unittest.mock import patch

class TestDocumentReuseIdempotency(FrappeTestCase):
    def _build_webhook_payload(self, leadgen_id, page_id="PAGE-IDEM-TEST", form_id="FORM-IDEM-TEST"):
        return {
            "object": "page",
            "entry": [{
                "id": page_id,
                "time": 1720000000,
                "changes": [{
                    "value": {
                        "ad_id": "TEST-AD-001",
                        "form_id": form_id,
                        "leadgen_id": leadgen_id,
                        "created_time": 1720000000,
                        "page_id": page_id,
                        "adset_id": "TEST-SET-001"
                    },
                    "field": "leadgen"
                }]
            }]
        }

    def _build_graph_payload(self, leadgen_id, suffix):
        return {
            "id": leadgen_id,
            "created_time": "2026-08-01T09:00:00+0000",
            "field_data": [
                {"name": "full_name", "values": [f"Reuse Test Lead {suffix}"]},
                {"name": "phone", "values": [f"+97155{''.join(str(ord(c) % 10) for c in suffix)[:7]}"]},
                {"name": "email", "values": [f"reuse.{suffix}@example.com"]},
                {"name": "visa_type", "values": ["Tourist"]},
                {"name": "destination", "values": ["USA"]},
            ],
            "form_id": "FORM-IDEM-TEST",
            "campaign_name": "Reuse Campaign",
            "campaign_id": "CAMP-REUSE-001",
            "adset_name": "Reuse Adset",
            "adset_id": "SET-REUSE-001",
            "ad_name": "Reuse Ad",
            "ad_id": "AD-REUSE-001",
        }

    def test_case_a_customer_exists_crm_lead_missing(self):
        suffix = frappe.generate_hash(length=10)
        leadgen_id = f"LOCAL-TEST-CASE-A-{suffix}"
        phone = f"+97155{''.join(str(ord(c) % 10) for c in suffix)[:7]}"
        email = f"reuse.{suffix}@example.com"

        cust = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": f"Existing Customer {suffix}",
            "customer_type": "Individual",
            "customer_group": "Individual",
            "mobile_no": phone,
            "email_id": email
        }).insert(ignore_permissions=True)
        frappe.db.commit()

        graph = self._build_graph_payload(leadgen_id, suffix)
        replay_payload(self._build_webhook_payload(leadgen_id))
        qname = frappe.db.get_value("Lead Intake Queue", {"source_lead_id": leadgen_id})

        with (
            patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()),
            patch("visa_crm.api.pipeline_stage_services.fetch_lead", return_value=graph),
            patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"),
        ):
            intake_processor.process_queue(qname)

        qdoc = frappe.get_doc("Lead Intake Queue", qname)
        self.assertEqual(qdoc.matched_customer, cust.name)
        self.assertTrue(qdoc.matched_lead)

    def test_case_b_crm_lead_exists_customer_missing(self):
        suffix = frappe.generate_hash(length=10)
        leadgen_id = f"LOCAL-TEST-CASE-B-{suffix}"
        phone = f"+97155{''.join(str(ord(c) % 10) for c in suffix)[:7]}"
        email = f"reuse.{suffix}@example.com"

        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "first_name": f"Existing Lead {suffix}",
            "lead_name": f"Existing Lead {suffix}",
            "facebook_lead_id": leadgen_id,
            "mobile_no": phone,
            "email": email
        }).insert(ignore_permissions=True)
        frappe.db.commit()

        graph = self._build_graph_payload(leadgen_id, suffix)
        replay_payload(self._build_webhook_payload(leadgen_id))
        qname = frappe.db.get_value("Lead Intake Queue", {"source_lead_id": leadgen_id})

        with (
            patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()),
            patch("visa_crm.api.pipeline_stage_services.fetch_lead", return_value=graph),
            patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"),
        ):
            intake_processor.process_queue(qname)

        qdoc = frappe.get_doc("Lead Intake Queue", qname)
        self.assertEqual(qdoc.matched_lead, lead.name)
        self.assertTrue(qdoc.matched_customer)

    def test_case_c_d_e_double_processing_reuses_visa_and_comm_event(self):
        suffix = frappe.generate_hash(length=10)
        leadgen_id = f"LOCAL-TEST-CASE-CDE-{suffix}"
        graph = self._build_graph_payload(leadgen_id, suffix)

        replay_payload(self._build_webhook_payload(leadgen_id))
        qname = frappe.db.get_value("Lead Intake Queue", {"source_lead_id": leadgen_id})

        with (
            patch("visa_crm.api.pipeline_stage_services.get_meta_settings", return_value=frappe._dict()),
            patch("visa_crm.api.pipeline_stage_services.fetch_lead", return_value=graph),
            patch("visa_crm.api.pipeline_stage_services.frappe.enqueue"),
        ):
            res1 = intake_processor.process_queue(qname)
            res2 = intake_processor.process_queue(qname)

        self.assertEqual(res1["lead"], res2["lead"])
        self.assertEqual(res1["customer"], res2["customer"])
        self.assertEqual(res1["visa_application"], res2["visa_application"])
        self.assertEqual(res1["communication_event"], res2["communication_event"])

        visa_count = frappe.db.count("Visa Application", {"lead": res1["lead"]})
        self.assertEqual(visa_count, 1)
