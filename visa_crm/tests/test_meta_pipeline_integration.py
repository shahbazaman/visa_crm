from unittest.mock import patch
import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api import intake_processor

class TestMetaPipelineIntegration(FrappeTestCase):
    def test_production_style_meta_lead_creates_complete_pipeline(self):
        suffix=frappe.generate_hash(length=10)
        leadgen_id=f"9900{suffix}"
        email=f"meta.{suffix}@example.com"
        phone=f"+97150{''.join(str(ord(char)%10) for char in suffix)[:7]}"
        queue=frappe.new_doc("Lead Intake Queue")
        queue.status="Lead Received"
        queue.source_lead_id=leadgen_id
        queue.event_type="leadgen"
        queue.page_id="PAGE-PRODUCTION"
        queue.form_id="FORM-WEBHOOK"
        queue.raw_payload=frappe.as_json({"value":{"leadgen_id":leadgen_id,"page_id":"PAGE-PRODUCTION","form_id":"FORM-WEBHOOK"},"change":{"field":"leadgen"}})
        queue.insert(ignore_permissions=True)
        graph={"id":leadgen_id,"created_time":"2026-07-29T10:00:00+0000","field_data":[{"name":"full_name","values":[f"Production Lead {suffix}"]},{"name":"phone","values":[phone]},{"name":"email","values":[email]},{"name":"visa_type","values":["Tourist"]},{"name":"destination","values":["UAE"]},{"name":"budget","values":["5000"]}],"form_id":"FORM-GRAPH","campaign_name":"Production Campaign","campaign_id":"CAM-100","adset_name":"Production Adset","adset_id":"SET-100","ad_name":"Production Ad","ad_id":"AD-100"}
        with patch("visa_crm.api.pipeline_stage_services.get_meta_settings",return_value=frappe._dict()),patch("visa_crm.api.pipeline_stage_services.fetch_lead",return_value=graph),patch("visa_crm.api.pipeline_stage_services.frappe.enqueue") as enqueue,patch("visa_crm.api.lead_assignment._is_working",return_value=True):
            result=intake_processor.process_queue(queue.name)
            queue.reload()
        self.assertTrue(result["ok"])
        self.assertEqual(queue.status,"Processed")
        self.assertTrue(queue.matched_lead)
        self.assertTrue(queue.matched_customer)
        self.assertTrue(queue.visa_application)
        self.assertTrue(queue.communication_event)
        self.assertTrue(queue.followup_reference)
        self.assertTrue(queue.assigned_employee)
        self.assertEqual(queue.ai_status,"Queued")
        self.assertEqual(queue.page_id,"PAGE-PRODUCTION")
        self.assertEqual(queue.form_id,"FORM-GRAPH")
        for field,value in {"campaign_name":"Production Campaign","campaign_id":"CAM-100","adset_name":"Production Adset","adset_id":"SET-100","ad_name":"Production Ad","ad_id":"AD-100"}.items():
            self.assertEqual(queue.get(field),value)
        lead=frappe.get_doc("CRM Lead",queue.matched_lead)
        self.assertEqual(lead.facebook_lead_id,leadgen_id)
        self.assertEqual(lead.facebook_form_id,"FORM-GRAPH")
        self.assertEqual(lead.mobile_no,phone)
        self.assertEqual(lead.email,email)
        self.assertEqual(lead.customer360,queue.matched_customer)
        customer=frappe.get_doc("Customer",queue.matched_customer)
        self.assertEqual(customer.crm_lead,lead.name)
        visa=frappe.get_doc("Visa Application",queue.visa_application)
        self.assertEqual(visa.lead,lead.name)
        self.assertEqual(visa.customer,customer.name)
        event=frappe.get_doc("Communication Event",queue.communication_event)
        self.assertEqual(event.lead,lead.name)
        self.assertEqual(event.customer,customer.name)
        self.assertEqual(event.visa_application,visa.name)
        self.assertTrue(frappe.db.exists("Lead Assignment",{"lead":lead.name,"assigned_to":queue.assigned_employee}))
        self.assertEqual(frappe.db.count("CRM Lead",{"facebook_lead_id":leadgen_id}),1)
        intake_processor.process_queue(queue.name)
        self.assertEqual(frappe.db.count("CRM Lead",{"facebook_lead_id":leadgen_id}),1)
        enqueue.assert_called_once()
        states=dict(frappe.get_all("Lead Intake Stage",filters={"queue":queue.name},fields=["stage","state"],as_list=True))
        for stage in ("GRAPH_DOWNLOAD","NORMALIZE","CUSTOMER360","CRM_LEAD","LEAD_WORKFLOW","VISA_APPLICATION","COMMUNICATION_EVENT","FOLLOW_UP","COUNSELOR_ASSIGNMENT","AI_DISPATCH"):
            self.assertEqual(states[stage],"COMPLETED")
