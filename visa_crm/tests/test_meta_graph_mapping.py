import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from visa_crm.api import meta_graph
from visa_crm.api.meta_mapping import normalize_lead

class TestMetaGraphAndMapping(unittest.TestCase):
    def test_fetch_lead_uses_graph_fields(self):
        response=SimpleNamespace(status_code=200,content=b"{}",json=lambda:{"id":"L1","field_data":[]})
        settings=SimpleNamespace(get_password=lambda key:"token")
        with patch.object(meta_graph.requests,"get",return_value=response) as get, patch.object(meta_graph,"_hydrate_names"), patch.object(meta_graph,"log_info"), patch.object(meta_graph,"meta_debug_log"):
            lead=meta_graph.fetch_lead("L1",settings,{"queue_name":"Q1"})
        self.assertEqual(lead["id"],"L1")
        self.assertIn("field_data",get.call_args.kwargs["params"]["fields"])

    def test_graph_error_raises_clean_exception(self):
        response=SimpleNamespace(status_code=400,content=b"{}",json=lambda:{"error":{"message":"bad token"}})
        settings=SimpleNamespace(get_password=lambda key:"token")
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
