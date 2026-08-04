import imaplib
import socket
import unittest
from unittest.mock import Mock,patch
import frappe
from visa_crm.api import email_account
from frappe.integrations.doctype.connected_app.connected_app import ConnectedApp

class TestEmailAccountSetup(unittest.TestCase):
    def data(self,**values):
        out={"service":"GMail","email_account_name":"Visa Sales","email_id":"sales@example.com","password":"abcd efgh ijkl mnop","enable_incoming":1,"enable_outgoing":1}
        out.update(values)
        return frappe._dict(out)

    def test_gmail_configuration_and_app_password_normalization(self):
        doc=email_account._build_account(self.data(),email_account.PROVIDERS["GMail"])
        self.assertEqual(doc.service,"GMail")
        self.assertEqual(doc.email_server,"imap.gmail.com")
        self.assertEqual(doc.incoming_port,993)
        self.assertEqual(doc.smtp_server,"smtp.gmail.com")
        self.assertEqual(doc.smtp_port,587)
        self.assertEqual(doc.password,"abcdefghijklmnop")
        self.assertTrue(doc.use_ssl)
        self.assertTrue(doc.use_tls)

    def test_outlook_uses_microsoft_365_endpoints(self):
        data=self.data(service="Outlook",password="not-an-app-password")
        doc=email_account._build_account(data,email_account.PROVIDERS["Outlook"])
        self.assertEqual(doc.service,"Outlook.com")
        self.assertEqual(doc.email_server,"outlook.office365.com")
        self.assertEqual(doc.smtp_server,"smtp.office365.com")
        self.assertEqual(doc.incoming_port,993)
        self.assertEqual(doc.smtp_port,587)

    def test_outgoing_only_never_tests_imap(self):
        doc=Mock(enable_incoming=0,enable_outgoing=1)
        with patch.object(email_account,"_test_direction") as test:
            self.assertEqual(email_account._test_connections(doc),{"outgoing":"connected"})
        test.assert_called_once_with(doc,"outgoing")

    def test_incoming_and_outgoing_are_diagnosed_separately(self):
        doc=Mock(enable_incoming=1,enable_outgoing=1)
        with patch.object(email_account,"_test_direction",side_effect=[None,socket.timeout("timed out")]):
            with self.assertRaises(email_account.ConnectionStageError) as failure:
                email_account._test_connections(doc)
        self.assertEqual(failure.exception.stage,"outgoing SMTP")

    def test_provider_errors_are_classified(self):
        auth=email_account.classify_connection_error(imaplib.IMAP4.error("AUTHENTICATIONFAILED"),"incoming IMAP","GMail")
        timeout=email_account.classify_connection_error(socket.timeout(),"outgoing SMTP","GMail")
        dns=email_account.classify_connection_error(socket.gaierror(),"incoming IMAP","GMail")
        self.assertEqual(auth["category"],"authentication")
        self.assertEqual(timeout["category"],"timeout")
        self.assertEqual(dns["category"],"dns")

    def test_secret_redaction(self):
        secret="abcd efgh ijkl mnop"
        text=email_account.redact_error(f"password={secret} access_token=token123 client_secret=secret456",(secret,))
        self.assertNotIn(secret,text)
        self.assertNotIn("token123",text)
        self.assertNotIn("secret456",text)

    def test_other_provider_names_remain_framework_compatible(self):
        expected={"Sendgrid":"Sendgrid","SparkPost":"SparkPost","Yahoo":"Yahoo Mail","Yandex":"Yandex.Mail"}
        self.assertEqual({key:email_account.PROVIDERS[key]["service"] for key in expected},expected)

    def test_outgoing_provider_rejects_incoming(self):
        with self.assertRaises(email_account.EmailSetupError):
            email_account._validate_input(self.data(service="Sendgrid"),email_account.PROVIDERS["Sendgrid"])

    def test_create_api_persists_standard_email_account(self):
        name="_Test Visa CRM Gmail Setup"
        if frappe.db.exists("Email Account",name):
            frappe.delete_doc("Email Account",name,force=True)
        data=self.data(email_account_name=name,email_id="visa-email-test@example.com",enable_incoming=0,enable_outgoing=1)
        try:
            with patch.object(email_account,"_test_connections",return_value={"outgoing":"connected"}):
                result=email_account.create_email_account(data)
            saved=frappe.get_doc("Email Account",result["name"])
            self.assertEqual(saved.service,"GMail")
            self.assertEqual(saved.smtp_server,"smtp.gmail.com")
            self.assertEqual(saved.get_password("password"),"abcdefghijklmnop")
            self.assertFalse(saved.enable_incoming)
            self.assertTrue(saved.enable_outgoing)
        finally:
            if frappe.db.exists("Email Account",name):
                frappe.delete_doc("Email Account",name,force=True)

    def test_connected_app_generates_production_callback(self):
        app=ConnectedApp({"doctype":"Connected App","provider_name":"Visa Gmail OAuth"})
        app.name="Visa Gmail OAuth"
        with patch("frappe.utils.get_url",return_value="https://middleeast.frappe.cloud"):
            app.validate()
        self.assertEqual(app.redirect_uri,"https://middleeast.frappe.cloud/api/method/frappe.integrations.doctype.connected_app.connected_app.callback/Visa Gmail OAuth")

    def test_oauth_readiness_requires_connected_app(self):
        doc=frappe._dict({"auth_method":"OAuth","connected_app":None,"connected_user":"administrator@example.com","backend_app_flow":0})
        result=email_account.oauth_readiness(doc)
        self.assertEqual(result["status"],"configuration_required")
        self.assertFalse(result["configured"])

    def test_expired_oauth_token_with_refresh_is_refreshable(self):
        token=Mock()
        token.is_expired.return_value=True
        app=Mock(redirect_uri="https://middleeast.frappe.cloud/oauth",get_token_cache=Mock(return_value=token))
        doc=frappe._dict({"auth_method":"OAuth","connected_app":"Visa Gmail OAuth","connected_user":"administrator@example.com","backend_app_flow":0})
        with patch("frappe.get_doc",return_value=app),patch.object(email_account,"_password_exists",side_effect=[True,True]):
            result=email_account.oauth_readiness(doc)
        self.assertEqual(result["status"],"refresh_required")
        self.assertTrue(result["configured"])
        self.assertTrue(result["refresh_available"])
