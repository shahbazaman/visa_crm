import json
from unittest.mock import patch
import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api import android_metadata

class TestAndroidMetadata(FrappeTestCase):
    def test_description_json_has_priority_and_validates(self):
        payload={"recording_id":"CALL-1","employee_id":"EMP-1","employee_name":"Counselor","customer_phone":"+971501234567","call_direction":"OUTGOING","start_time":"2026-07-31T10:00:00+05:30","end_time":"2026-07-31T10:01:00+05:30","duration_seconds":60,"app_version":"1.0.0","sha256":"a"*64}
        result=android_metadata.extract_metadata_from_description(json.dumps(payload))
        self.assertEqual(result["metadata"]["call_direction"],"Outbound")
        self.assertEqual(android_metadata.validate_metadata(result["metadata"]),[])

    def test_invalid_metadata_returns_warnings_without_raising(self):
        result=android_metadata.extract_metadata_from_description('{"recording_id":"CALL-2","duration_seconds":0}')
        warnings=android_metadata.validate_metadata(result["metadata"])
        self.assertTrue(any("employee_id" in row for row in warnings))
        self.assertTrue(any("duration_seconds" in row for row in warnings))

    def test_hash_mismatch_is_reported(self):
        with patch("visa_crm.api.android_metadata.get_file_path",return_value=__file__):
            result=android_metadata.calculate_hash_if_missing("/private/files/call.mp3",{"sha256":"a"*64})
        self.assertFalse(result["matches"])

    def test_recording_prefix_pairs_both_upload_orders(self):
        self.assertEqual(android_metadata._recording_prefix("CALL-20260731-114523-4F9A2C_EMP_EMP03.mp3"),"CALL-20260731-114523-4F9A2C")
        self.assertEqual(android_metadata._recording_prefix("CALL-20260731-114523-4F9A2C_metadata.json"),"CALL-20260731-114523-4F9A2C")

    def test_metadata_first_pairs_available_audio(self):
        metadata_file=frappe._dict({"doctype":"File","name":"META-FILE","file_name":"CALL-20260731-114523-4F9A2C_metadata.json","file_url":"/private/files/meta.json"})
        metadata_file.meta=frappe._dict({"has_field":lambda field:False})
        audio=frappe._dict({"doctype":"File","name":"AUDIO-FILE","file_name":"CALL-20260731-114523-4F9A2C_EMP_EMP03.mp3","file_url":"/private/files/call.mp3"})
        with patch("visa_crm.api.android_metadata.load_metadata",return_value={"metadata":{"recording_id":"CALL-20260731-114523-4F9A2C"},"raw":"{}","source":"metadata_file"}),patch("visa_crm.api.android_metadata._audio_files_for_prefix",return_value=[audio]),patch("visa_crm.api.android_metadata.enrich_audio_file",return_value="CI-1") as enrich:
            result=android_metadata.pair_audio_with_metadata(metadata_file)
        self.assertEqual(result,["CI-1"])
        enrich.assert_called_once()

    def test_audio_first_uses_description_or_waits_for_companion(self):
        audio=frappe._dict({"doctype":"File","name":"AUDIO-FILE","file_name":"CALL-20260731-114523-4F9A2C_EMP_EMP03.mp3","file_url":"/private/files/call.mp3"})
        with patch("visa_crm.api.android_metadata.extract_metadata",return_value={"metadata":{},"source":"filename","warnings":[]}),patch("visa_crm.api.android_metadata.enrich_audio_file",return_value="CI-1") as enrich:
            result=android_metadata.pair_audio_with_metadata(audio)
        self.assertEqual(result,["CI-1"])
        enrich.assert_called_once()

    def test_employee_lookup_prefers_employee_id(self):
        meta=frappe._dict({"has_field":lambda field:field in ("employee_number","employee_name","user_id","company_email")})
        with patch("visa_crm.api.android_metadata.frappe.db.exists",return_value=True),patch("visa_crm.api.android_metadata.frappe.db.get_value",return_value="employee@example.com"),patch("visa_crm.api.android_metadata.frappe.get_meta",return_value=meta):
            employee,user=android_metadata._employee({"employee_id":"EMP-0001"})
        self.assertEqual(employee,"EMP-0001")
        self.assertEqual(user,"employee@example.com")
