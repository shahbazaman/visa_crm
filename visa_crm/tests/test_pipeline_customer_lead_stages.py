import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api.pipeline_engine import ensure_stage_ledger
from visa_crm.api.pipeline_stage_services import crm_lead,customer360

class TestPipelineCustomerLeadStages(FrappeTestCase):
    def setUp(self):
        self.source=f"C360-{frappe.generate_hash(length=10)}"
        self.phone=f"+9715{''.join(str(ord(char)%10) for char in self.source)[:8]}"
        self.email=f"{self.source.lower()}@example.com"
        doc=frappe.new_doc("Lead Intake Queue")
        doc.source_lead_id=self.source
        doc.status="Lead Downloaded"
        doc.raw_payload="{}"
        doc.normalized_payload=frappe.as_json(self._data())
        doc.normalized_payload_hash=frappe.generate_hash(length=32)
        doc.insert(ignore_permissions=True)
        self.queue=doc.name
        ensure_stage_ledger(self.queue)
        frappe.db.commit()

    def tearDown(self):
        lead=frappe.db.get_value("CRM Lead",{"facebook_lead_id":self.source},"name")
        customer=frappe.db.get_value("Lead Intake Queue",self.queue,"matched_customer")
        frappe.db.delete("Lead Intake Stage",{"queue":self.queue})
        frappe.db.delete("Customer Identity",{"customer":customer}) if customer else None
        frappe.db.delete("CRM Lead",{"name":lead}) if lead else None
        frappe.db.delete("Customer",{"name":customer}) if customer else None
        frappe.db.delete("Lead Intake Queue",{"name":self.queue})
        frappe.db.commit()

    def test_neither_exists_creates_and_links_exactly_once(self):
        customer=customer360(self.queue)["customer"]
        lead=crm_lead(self.queue)["lead"]
        self.assertEqual(frappe.db.get_value("CRM Lead",lead,"customer360"),customer)
        self.assertEqual(frappe.db.get_value("Customer",customer,"crm_lead"),lead)
        self.assertEqual(frappe.db.count("CRM Lead",{"facebook_lead_id":self.source}),1)
        self.assertEqual(customer360(self.queue)["customer"],customer)
        self.assertEqual(crm_lead(self.queue)["lead"],lead)
        self.assertEqual(frappe.db.count("CRM Lead",{"facebook_lead_id":self.source}),1)

    def test_existing_customer_still_creates_lead(self):
        customer=frappe.new_doc("Customer")
        customer.customer_name="Existing Customer"
        if customer.meta.has_field("mobile_no"):
            customer.mobile_no=self.phone
        customer.insert(ignore_permissions=True)
        resolved=customer360(self.queue)["customer"]
        lead=crm_lead(self.queue)["lead"]
        self.assertEqual(resolved,customer.name)
        self.assertEqual(frappe.db.get_value("CRM Lead",lead,"customer360"),customer.name)

    def test_existing_lead_without_customer_creates_and_repairs_customer(self):
        from visa_crm.api.lead_creator import create_crm_lead
        lead=create_crm_lead(self._data(),{"queue_name":self.queue,"source_lead_id":self.source})
        customer=customer360(self.queue)["customer"]
        resolved=crm_lead(self.queue)["lead"]
        self.assertEqual(resolved,lead)
        self.assertEqual(frappe.db.get_value("CRM Lead",lead,"customer360"),customer)

    def _data(self):
        return {"source_lead_id":self.source,"form_id":"FORM-1","page_id":"PAGE-1","customer_name":"Stage Customer","phone":self.phone,"email":self.email,"campaign_id":"CAM-1","campaign_name":"Campaign","meta_fields":{"full_name":"Stage Customer","phone":self.phone,"email":self.email},"meta_raw_fields":frappe.as_json({"full_name":"Stage Customer","phone":self.phone,"email":self.email})}
