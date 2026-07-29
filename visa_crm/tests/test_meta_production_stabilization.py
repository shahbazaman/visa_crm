import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock,patch
from visa_crm.api import customer360,intake_processor,lead_creator

class QueueDoc:
    def __init__(self):
        self.name="LIQ-PRODUCTION-TEST"
        self.source_lead_id="META-REAL-1001"
        self.status="Lead Received"
        self.page_id="PAGE-1001"
        self.form_id="FORM-WEBHOOK"
    def get(self,field):
        return getattr(self,field,None)
    def reload(self):
        return self

class TestMetaProductionStabilization(unittest.TestCase):
    def test_facebook_identity_is_mapped_to_crm_lead(self):
        values=lead_creator._lead_values({"source_lead_id":"META-REAL-1001","form_id":"FORM-1001","customer_name":"Nabeel Afi","phone":"+919037764668"},{}, "Nabeel Afi","Meta Instant Form")
        self.assertEqual(values["facebook_lead_id"],"META-REAL-1001")
        self.assertEqual(values["facebook_form_id"],"FORM-1001")

    def test_customer360_always_returns_lead_and_customer(self):
        combinations=((None,None),("CRM-EXISTING",None),(None,"CUSTOMER-EXISTING"),("CRM-EXISTING","CUSTOMER-EXISTING"))
        for lead,customer in combinations:
            with self.subTest(lead=lead,customer=customer),patch.object(customer360,"match_lead_data",return_value={"lead":lead,"customer":customer}),patch.object(customer360,"create_crm_lead",return_value="CRM-CREATED") as create_lead,patch.object(customer360,"create_customer_from_lead",return_value="CUSTOMER-CREATED") as create_customer,patch.object(customer360,"_link_lead_customer") as link:
                result=customer360.link_or_create_lead({"source_lead_id":"META-REAL-1001"})
                self.assertTrue(result["lead"])
                self.assertTrue(result["customer"])
                create_lead.assert_called_once() if not lead else create_lead.assert_not_called()
                create_customer.assert_called_once() if not customer else create_customer.assert_not_called()
                link.assert_called_once_with(result["lead"],result["customer"])

    def test_meta_lead_does_not_reuse_lead_by_phone_when_identity_is_new(self):
        with patch.object(customer360,"has_doctype",return_value=True),patch.object(customer360,"has_field",return_value=True),patch.object(customer360.frappe.db,"get_value",return_value=None) as get_value:
            result=customer360._match("CRM Lead",["+971501234567"],["same@example.com"],"Same Customer","META-NEW")
        self.assertIsNone(result)
        get_value.assert_called_once_with("CRM Lead",{"facebook_lead_id":"META-NEW"},"name")

    def test_queue_preserves_webhook_page_and_all_meta_context(self):
        doc=QueueDoc()
        data={"source_lead_id":"META-REAL-1001","customer_name":"Nabeel Afi","phone":"+919037764668","form_id":"FORM-GRAPH","campaign_name":"Summer Visa","campaign_id":"CAM-1","adset_name":"Dubai","adset_id":"SET-1","ad_name":"Travel Now","ad_id":"AD-1","custom_answers":{"full_name":"Nabeel Afi"}}
        written={}
        with patch.object(intake_processor,"set_values",side_effect=lambda doctype,name,values:written.update(values)),patch.object(intake_processor,"_sync_webhook_event"),patch.object(intake_processor,"meta_debug_log"):
            intake_processor._update_queue(doc,data,{"id":"META-REAL-1001"},"Lead Downloaded")
        self.assertEqual(written["page_id"],"PAGE-1001")
        self.assertEqual(written["form_id"],"FORM-GRAPH")
        for field in ("campaign_name","campaign_id","adset_name","adset_id","ad_name","ad_id"):
            self.assertEqual(written[field],data[field])

    def test_stale_fetching_queue_is_recovered(self):
        cursor=SimpleNamespace(rowcount=1)
        db=SimpleNamespace(sql=Mock(),_cursor=cursor,commit=Mock())
        with patch.object(intake_processor,"has_field",return_value=True),patch.object(intake_processor,"now_datetime",return_value=datetime(2026,7,29,12,0)),patch.object(intake_processor.frappe,"db",db),patch.object(intake_processor,"log_info"):
            recovered=intake_processor._recover_stale_fetches()
        self.assertEqual(recovered,1)
        db.commit.assert_called_once()
