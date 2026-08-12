import frappe
import json
import unittest
from visa_crm.api import android_sync, android_metadata

class TestAndroidSyncIdempotency(unittest.TestCase):
    def test_01_metadata_direction_normalization(self):
        normalized = android_metadata._normalize({
            "recording_id": "CALL-20260812-999999-TEST01",
            "call_direction": "INCOMING",
            "duration_seconds": 15
        })
        self.assertEqual(normalized["call_direction"], "Inbound")

        warnings = android_metadata.validate_metadata(normalized)
        # Verify INCOMING normalization leaves no direction warning
        self.assertNotIn("call_direction must be INCOMING or OUTGOING", warnings)

    def test_02_idempotent_audio_upload_reuses_existing_file(self):
        h = frappe.generate_hash(length=6).upper()
        recording_id = f"CALL-20260812-161549-{h}"
        filename = f"{recording_id}_EMP_emp06_Rizwan_CUST_919567194946_Inbound.mp3"
        import base64
        b64_audio = base64.b64encode(b"IDEMPOTENT_AUDIO_HEADER_DUMMY_MP3_PAYLOAD_CONTENT_12345").decode()

        # 1st Upload: should create file
        res1 = android_sync.upload_call_audio(
            recording_id=recording_id,
            filename=filename,
            filedata=b64_audio
        )
        self.assertTrue(res1["ok"])
        self.assertEqual(res1["status"], "CREATED")
        first_file_doc = res1["file_name_doc"]

        # 2nd Upload (Retry): must REUSE existing file
        res2 = android_sync.upload_call_audio(
            recording_id=recording_id,
            filename=filename,
            filedata=b64_audio
        )
        self.assertTrue(res2["ok"])
        self.assertTrue(res2["reused"])
        self.assertEqual(res2["status"], "EXISTS")
        self.assertEqual(res2["file_name_doc"], first_file_doc)

    def test_03_preflight_and_metadata_sync_retry_resuming(self):
        h = frappe.generate_hash(length=6).upper()
        recording_id = f"CALL-20260812-161559-{h}"
        filename = f"{recording_id}_EMP_emp06_Rizwan_CUST_919567194946_Inbound.mp3"
        import base64
        dummy_audio = base64.b64encode(b"DUMMY_AUDIO_BYTES_TEST_STAGE").decode()

        # Step 1: Upload audio
        u1 = android_sync.upload_call_audio(recording_id=recording_id, filename=filename, filedata=dummy_audio)
        self.assertTrue(u1["ok"])

        # Step 2: Pre-flight check
        status = android_sync.check_call_status(recording_id=recording_id, file_name=filename)
        self.assertTrue(status["audio_uploaded"])
        self.assertEqual(status["recording_file_url"], u1["file_url"])

        # Step 3: Metadata sync (with INCOMING direction)
        meta_payload = {
            "recording_id": recording_id,
            "call_uuid": recording_id,
            "employee_id": "HR-EMP-00006",
            "employee_name": "Rizwan",
            "customer_phone": "919567194946",
            "call_direction": "INCOMING",
            "duration_seconds": 25,
            "app_version": "1.0.0"
        }
        m1 = android_sync.sync_call_metadata(recording_id, meta_payload)
        self.assertTrue(m1["ok"])
        self.assertEqual(m1["status"], "SUCCESS")

        ci_name = m1["call_intelligence_name"]
        ci_doc = frappe.get_doc("Call Intelligence", ci_name)
        self.assertEqual(ci_doc.call_direction, "Inbound")

        # Step 4: Retry metadata sync (simulate WorkManager retry of stage 2)
        m2 = android_sync.sync_call_metadata(recording_id, meta_payload)
        self.assertTrue(m2["ok"])
        self.assertEqual(m2["call_intelligence_name"], ci_name)
