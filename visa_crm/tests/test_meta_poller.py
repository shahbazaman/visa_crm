import unittest
from unittest.mock import patch, MagicMock
import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api import meta_poller

class TestMetaPoller(FrappeTestCase):
    @patch("visa_crm.api.meta_poller.get_configured_access_token", return_value=("TEST_TOKEN_123", "504890496038695"))
    @patch("visa_crm.api.meta_poller.requests.get")
    def test_get_page_lead_forms(self, mock_get, mock_token):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {"id": "2148691029027696", "name": "Malaysia Lead Form", "status": "ACTIVE", "leads_count": 10}
            ]
        }
        mock_get.return_value = mock_resp

        forms = meta_poller.get_page_lead_forms()
        self.assertTrue(len(forms) >= 1)
        self.assertEqual(forms[0]["id"], "2148691029027696")

    @patch("visa_crm.api.meta_poller.get_configured_access_token", return_value=("TEST_TOKEN_123", "504890496038695"))
    @patch("visa_crm.api.meta_poller.requests.get")
    def test_fetch_form_leads(self, mock_get, mock_token):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {"id": "99990001", "created_time": "2026-08-17T10:00:00+0000", "field_data": [{"name": "full_name", "values": ["Test Polled Lead"]}]}
            ]
        }
        mock_get.return_value = mock_resp

        leads = meta_poller.fetch_form_leads("2148691029027696")
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]["id"], "99990001")

    @patch("visa_crm.api.meta_poller.get_configured_access_token", return_value=("TEST_TOKEN_123", "504890496038695"))
    @patch("visa_crm.api.meta_poller.requests.post")
    def test_subscribe_page_webhooks(self, mock_post, mock_token):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"success": true}'
        mock_resp.json.return_value = {"success": True}
        mock_post.return_value = mock_resp

        res = meta_poller.subscribe_page_webhooks()
        self.assertTrue(res.get("ok"))
