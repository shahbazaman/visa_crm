import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from visa_crm.api import meta_graph
from visa_crm.api import lead_creator
from visa_crm.api.meta_mapping import normalize_lead

class TestMetaGraphAndMapping(unittest.TestCase):
    def test_fetch_lead_uses_graph_fields(self):
        response=SimpleNamespace(status_code=200,content=b"{}",json=lambda:{"id":"L1","field_data":[]})
        settings=SimpleNamespace(get_password=lambda key,raise_exception=False:"token")
        with patch.object(meta_graph.requests,"get",return_value=response) as get, patch.object(meta_graph,"_hydrate_names"), patch.object(meta_graph,"log_info"), patch.object(meta_graph,"meta_debug_log"):
            lead=meta_graph.fetch_lead("L1",settings,{"queue_name":"Q1"})
        self.assertEqual(lead["id"],"L1")
        self.assertIn("field_data",get.call_args.kwargs["params"]["fields"])

    def test_graph_error_raises_clean_exception(self):
        response=SimpleNamespace(status_code=400,content=b"{}",json=lambda:{"error":{"message":"bad token"}})
        settings=SimpleNamespace(get_password=lambda key,raise_exception=False:"token")
        with patch.object(meta_graph.requests,"get",return_value=response), patch.object(meta_graph,"meta_debug_log"):
            with self.assertRaises(meta_graph.MetaGraphError):
                meta_graph.fetch_lead("L1",settings,{})

    def test_normalize_lead_maps_standard_meta_fields(self):
        payload={"id":"L1","field_data":[{"name":"full_name","values":["Sara Test"]},{"name":"phone_number","values":["050 111 2222"]},{"name":"email","values":["SARA@EXAMPLE.COM"]},{"name":"which_country_are_you_interested_in?","values":["Canada"]},{"name":"visa_type","values":["Student"]},{"name":"നിങ്ങളുടെ_budget_എത്രയാണ്?","values":["5000"]},{"name":"destination","values":["Dubai"]},{"name":"do_you_have_a_valid_passport?","values":["Valid"]},{"name":"ബാലി_trip_ഏത്_മാസം_പ്ലാൻ_ചെയ്യുന്നു?","values":["November"]},{"name":"message","values":["Need tourist visa"]},{"name":"unmapped_form_answer","values":["Keep me"]}],"campaign_name":"Campaign","ad_name":"Ad"}
        data=normalize_lead(payload,None,{"queue_name":"Q1"})
        self.assertEqual(data["source_lead_id"],"L1")
        self.assertEqual(data["customer_name"],"Sara Test")
        self.assertEqual(data["email"],"sara@example.com")
        self.assertEqual(data["country_interested"],"Canada")
        self.assertEqual(data["custom_budget"],"5000")
        self.assertEqual(data["custom_destination"],"Dubai")
        self.assertEqual(data["custom_passport_status"],"Valid")
        self.assertEqual(data["custom_travel_month"],"November")
        self.assertEqual(data["notes"],"Need tourist visa")
        self.assertIn("unmapped_form_answer",data["meta_raw_fields"])

    def test_meta_fields_are_assigned_to_crm_lead(self):
        payload={"id":"L2","field_data":[{"name":"full_name","values":["John Doe"]},{"name":"phone","values":["+971501234567"]},{"name":"email","values":["john@example.com"]}]}
        data=normalize_lead(payload,None,{"queue_name":"Q2"})
        lead=FakeLead()
        with patch.object(lead_creator.frappe,"new_doc",return_value=lead), patch.object(lead_creator.frappe,"logger",return_value=Mock()), patch.object(lead_creator,"_ensure_link_master"), patch.object(lead_creator,"meta_debug_log"):
            name=lead_creator.create_crm_lead(data,{"queue_name":"Q2"})
        self.assertEqual(name,"CRM-LEAD-TEST")
        self.assertEqual(lead.get("lead_name"),"John Doe")
        self.assertEqual(lead.get("first_name"),"John Doe")
        self.assertEqual(lead.get("mobile_no"),"+971501234567")
        self.assertEqual(lead.get("email"),"john@example.com")

class FakeMeta:
    title_field=None
    def has_field(self, field):
        return True
    def get_field(self, field):
        return SimpleNamespace(fieldtype="Data",options=None)
    def get(self, field):
        return []

class FakeLead:
    def __init__(self):
        self.name="CRM-LEAD-TEST"
        self.meta=FakeMeta()
        self.values={}
    def get(self, field):
        return self.values.get(field)
    def set(self, field, value):
        self.values[field]=value
    def as_dict(self):
        return dict(self.values)
    def insert(self, **kwargs):
        return self
    def reload(self):
        return self
