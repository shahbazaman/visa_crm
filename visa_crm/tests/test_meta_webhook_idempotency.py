import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api.meta_webhook import replay_payload

class TestMetaWebhookIdempotency(FrappeTestCase):
    def setUp(self):
        self.source=f"WEBHOOK-{frappe.generate_hash(length=12)}"
        self.payload={"object":"page","entry":[{"id":"PAGE-IDEMPOTENT","changes":[{"field":"leadgen","value":{"leadgen_id":self.source,"page_id":"PAGE-IDEMPOTENT","form_id":"FORM-IDEMPOTENT"}}]}]}

    def tearDown(self):
        queue=frappe.db.get_value("Lead Intake Queue",{"source_lead_id":self.source},"name")
        if queue:
            frappe.db.delete("Lead Intake Stage",{"queue":queue})
            frappe.db.delete("Lead Intake Queue",{"name":queue})
        if frappe.db.exists("DocType","Meta Webhook Event"):
            frappe.db.delete("Meta Webhook Event",{"leadgen_id":self.source})
        frappe.db.commit()

    def test_duplicate_delivery_creates_one_canonical_queue(self):
        first=replay_payload(self.payload)
        second=replay_payload(self.payload)
        self.assertEqual(first["stored"],1)
        self.assertEqual(second["duplicates"],1)
        self.assertEqual(frappe.db.count("Lead Intake Queue",{"source_lead_id":self.source}),1)
        queue=frappe.get_doc("Lead Intake Queue",{"source_lead_id":self.source})
        self.assertEqual(queue.page_id,"PAGE-IDEMPOTENT")
        self.assertEqual(queue.form_id,"FORM-IDEMPOTENT")
        if frappe.db.exists("DocType","Meta Webhook Event"):
            events=frappe.get_all("Meta Webhook Event",filters={"leadgen_id":self.source},fields=["queue"])
            self.assertEqual(len(events),2)
            self.assertTrue(all(row.queue==queue.name for row in events))

    def test_meta_verify_valid_token(self):
        from visa_crm.api.meta_webhook import meta_verify, _get_password_safe
        settings = frappe.get_doc("Meta Settings", frappe.get_all("Meta Settings", pluck="name")[0])
        token = _get_password_safe(settings, "verify_token") or "visa_crm_verify_2026"
        frappe.local.request = frappe._dict(
            args=frappe._dict({
                "hub.mode": "subscribe",
                "hub.verify_token": token,
                "hub.challenge": "123456789"
            })
        )
        response = meta_verify()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/plain")
        self.assertEqual(response.get_data(as_text=True), "123456789")

    def test_meta_verify_invalid_token(self):
        from visa_crm.api.meta_webhook import meta_verify
        frappe.local.request = frappe._dict(
            args=frappe._dict({
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong_verify_token_123",
                "hub.challenge": "123456789"
            })
        )
        response = meta_verify()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.mimetype, "text/plain")
        self.assertEqual(response.get_data(as_text=True), "Verification failed")

