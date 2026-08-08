import unittest
from unittest.mock import patch, Mock
import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api import meta_graph
from visa_crm.api.pipeline_engine import ensure_stage_ledger
from visa_crm.api.pipeline_stage_services import graph_download

class TestGraphDownloadResilience(FrappeTestCase):
    def setUp(self):
        doc = frappe.new_doc("Lead Intake Queue")
        doc.source_lead_id = "1728701815047004"
        doc.status = "Lead Received"
        doc.raw_payload = '{"source_lead_id": "1728701815047004", "leadgen_id": "1728701815047004"}'
        doc.insert(ignore_permissions=True)
        self.queue = doc.name
        ensure_stage_ledger(self.queue)
        frappe.db.commit()

    def tearDown(self):
        frappe.db.delete("Lead Intake Stage", {"queue": self.queue})
        frappe.db.delete("Lead Intake Queue", {"name": self.queue})
        frappe.db.commit()

    def test_valid_lead_id_passed_to_fetch_lead(self):
        payload = {"id": "1728701815047004", "field_data": [{"name": "full_name", "values": ["Test Person"]}]}
        with patch("visa_crm.api.pipeline_stage_services.fetch_lead", return_value=payload) as mock_fetch:
            res = graph_download(self.queue)
            mock_fetch.assert_called_once()
            args, _ = mock_fetch.call_args
            self.assertEqual(args[0], "1728701815047004")
            self.assertNotEqual(args[0], "None")
            self.assertEqual(res["graph_payload"], payload)

    def test_missing_lead_id_fails_safely_without_http_get_none(self):
        frappe.db.set_value("Lead Intake Queue", self.queue, {"source_lead_id": None, "raw_payload": "{}"})
        with patch("visa_crm.api.meta_graph.requests.get") as mock_get:
            with self.assertRaises(ValueError) as ctx:
                graph_download(self.queue)
            self.assertIn("Meta leadgen ID is missing", str(ctx.exception))
            mock_get.assert_not_called()

    def test_source_lead_id_recovery_from_raw_payload(self):
        frappe.db.set_value("Lead Intake Queue", self.queue, {"source_lead_id": "None", "raw_payload": '{"source_lead_id": "1728701815047004"}'})
        payload = {"id": "1728701815047004", "field_data": []}
        with patch("visa_crm.api.pipeline_stage_services.fetch_lead", return_value=payload) as mock_fetch:
            res = graph_download(self.queue)
            mock_fetch.assert_called_once()
            self.assertEqual(mock_fetch.call_args[0][0], "1728701815047004")
            recovered = frappe.db.get_value("Lead Intake Queue", self.queue, "source_lead_id")
            self.assertEqual(recovered, "1728701815047004")

    def test_fetch_lead_rejects_none_string(self):
        with patch("visa_crm.api.meta_graph.requests.get") as mock_get:
            with self.assertRaises(meta_graph.MetaGraphError) as ctx:
                meta_graph.fetch_lead("None")
            self.assertIn("Meta leadgen ID is missing or invalid", str(ctx.exception))
            mock_get.assert_not_called()
