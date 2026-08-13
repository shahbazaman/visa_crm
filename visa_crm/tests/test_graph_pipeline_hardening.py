"""
Regression tests for Meta pipeline hardening (Tasks 1-5).

  1. Stale graph error fields are cleared after successful retry.
  2. ATTR-* / synthetic IDs are rejected before Graph API is called.
  3. Empty reconstructed payload is rejected.
  4. Valid reconstruction with evidence succeeds.
  5. _hydrate_names() failures are isolated from primary success.
  6. Permanent Graph failure + no evidence -> NORMALIZE is SKIPPED.
  7. Permanent Graph failure + PII evidence -> NORMALIZE is NOT skipped.
  8. Non-permanent failure does NOT cascade.
  9. Real numeric Meta leadgen IDs pass through unchanged.
 10. is_synthetic_leadgen_id classifies correctly.
"""
import json
from unittest.mock import MagicMock, patch
import frappe
from frappe.tests.utils import FrappeTestCase

from visa_crm.api.meta_graph import (
    MetaGraphError,
    PermanentGraphError,
    is_synthetic_leadgen_id,
    fetch_lead,
)
from visa_crm.api.pipeline_engine import ensure_stage_ledger
from visa_crm.api.pipeline_stage_services import (
    _graph_payload_from_queue,
    graph_download,
    graph_failure,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique_real_leadgen_id():
    """Return a unique 16-digit numeric ID that passes is_synthetic_leadgen_id=False.
    Uses a fixed prefix '1584' + 12-digit frappe hash to guarantee uniqueness.
    """
    suffix = frappe.generate_hash(length=12)
    # Ensure it is 16 chars and fully numeric by converting hash to decimal.
    numeric = str(int(suffix, 16) % (10 ** 12)).zfill(12)
    return "1584" + numeric


def _make_queue(source_lead_id=None, raw_payload=None,
                custom_answers=None, customer_name=None, phone=None, email=None):
    sid = source_lead_id or _unique_real_leadgen_id()
    doc = frappe.new_doc("Lead Intake Queue")
    doc.source_lead_id = sid
    doc.status = "Lead Received"
    doc.raw_payload = raw_payload or json.dumps(
        {"source_lead_id": sid, "leadgen_id": sid}
    )
    if custom_answers:
        doc.custom_answers = json.dumps(custom_answers)
    if customer_name:
        doc.customer_name = customer_name
    if phone:
        doc.phone = phone
    if email:
        doc.email = email
    doc.insert(ignore_permissions=True)
    ensure_stage_ledger(doc.name)
    frappe.db.commit()
    return doc.name


def _set_graph_error_fields(queue_name, code=100, subcode=33, message="Old error"):
    meta = frappe.get_meta("Lead Intake Queue")
    values = {}
    if meta.has_field("graph_error_code"):
        values["graph_error_code"] = code
    if meta.has_field("graph_error_subcode"):
        values["graph_error_subcode"] = subcode
    if meta.has_field("graph_error_message"):
        values["graph_error_message"] = message
    if values:
        frappe.db.set_value("Lead Intake Queue", queue_name, values, update_modified=False)
        frappe.db.commit()


def _get_graph_error_fields(queue_name):
    meta = frappe.get_meta("Lead Intake Queue")
    fields = [f for f in ("graph_error_code", "graph_error_subcode", "graph_error_message")
              if meta.has_field(f)]
    if not fields:
        return {}
    return frappe.db.get_value("Lead Intake Queue", queue_name, fields, as_dict=True) or {}


def _cleanup(queue_name):
    frappe.db.delete("Lead Intake Stage", {"queue": queue_name})
    frappe.db.delete("Lead Intake Queue", {"name": queue_name})
    frappe.db.commit()


# ---------------------------------------------------------------------------
# 1. is_synthetic_leadgen_id classification
# ---------------------------------------------------------------------------

class TestSyntheticIdDetection(FrappeTestCase):
    def test_attr_prefix_is_synthetic(self):
        for val in ("ATTR-4aafda9a", "attr-00001234", "ATTR-xyz"):
            with self.subTest(val=val):
                self.assertTrue(is_synthetic_leadgen_id(val))

    def test_manual_prefix_is_synthetic(self):
        self.assertTrue(is_synthetic_leadgen_id("manual-12345"))

    def test_test_prefix_is_synthetic(self):
        self.assertTrue(is_synthetic_leadgen_id("test-lead-001"))

    def test_hex_string_is_synthetic(self):
        # Hex strings like CRM test scaffolding IDs are not real Meta IDs
        self.assertTrue(is_synthetic_leadgen_id("99001634a84745"))

    def test_real_meta_ids_not_synthetic(self):
        for val in ("1584030679973165", "1728701815047004", "2097717174290481"):
            with self.subTest(val=val):
                self.assertFalse(is_synthetic_leadgen_id(val))

    def test_empty_not_synthetic(self):
        self.assertFalse(is_synthetic_leadgen_id(""))
        self.assertFalse(is_synthetic_leadgen_id(None))

    def test_short_numeric_is_synthetic(self):
        # Real Meta IDs are always >= 13 digits; short numerics are not real.
        self.assertTrue(is_synthetic_leadgen_id("123456"))
        self.assertTrue(is_synthetic_leadgen_id("1234567890"))

    def test_exactly_13_digits_is_not_synthetic(self):
        # 13 digits is the minimum for a real Meta ID.
        self.assertFalse(is_synthetic_leadgen_id("1000000000001"))

    def test_fake_prefix_is_synthetic(self):
        self.assertTrue(is_synthetic_leadgen_id("fake-abc123"))

    def test_dummy_prefix_is_synthetic(self):
        self.assertTrue(is_synthetic_leadgen_id("dummy-xyz"))


# ---------------------------------------------------------------------------
# 2. fetch_lead() rejects synthetic IDs without HTTP call
# ---------------------------------------------------------------------------

class TestFetchLeadSyntheticIdRejection(FrappeTestCase):
    def test_attr_raises_permanent_no_http(self):
        with patch("visa_crm.api.meta_graph.requests.get") as mock_get:
            with self.assertRaises(PermanentGraphError) as ctx:
                fetch_lead("ATTR-4aafda9a")
            mock_get.assert_not_called()
            self.assertIn("synthetic/internal", str(ctx.exception))
            self.assertIn("ATTR-4aafda9a", str(ctx.exception))

    def test_manual_raises_permanent_no_http(self):
        with patch("visa_crm.api.meta_graph.requests.get") as mock_get:
            with self.assertRaises(PermanentGraphError):
                fetch_lead("manual-test-001")
            mock_get.assert_not_called()

    def test_short_numeric_raises_permanent_no_http(self):
        with patch("visa_crm.api.meta_graph.requests.get") as mock_get:
            with self.assertRaises(PermanentGraphError):
                fetch_lead("12345")
            mock_get.assert_not_called()

    def test_real_id_reaches_graph_api(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"id":"1584030679973165","field_data":[]}' 
        mock_resp.json.return_value = {"id": "1584030679973165", "field_data": []}
        with patch("visa_crm.api.meta_graph.requests.get", return_value=mock_resp):
            with patch("visa_crm.api.meta_graph._access_token", return_value="FAKE-TOKEN"):
                result = fetch_lead("1584030679973165")
        self.assertEqual(result["id"], "1584030679973165")

    def test_real_id_not_mutated_in_url(self):
        captured = {}
        def fake_get(url, params=None, timeout=None):
            captured["url"] = url
            resp = MagicMock()
            resp.status_code = 200
            resp.content = b'{"id":"1728701815047004","field_data":[]}' 
            resp.json.return_value = {"id": "1728701815047004", "field_data": []}
            return resp
        with patch("visa_crm.api.meta_graph.requests.get", side_effect=fake_get):
            with patch("visa_crm.api.meta_graph._access_token", return_value="FAKE-TOKEN"):
                fetch_lead("1728701815047004")
        self.assertIn("1728701815047004", captured["url"])
        self.assertNotIn("None", captured["url"])


# ---------------------------------------------------------------------------
# 1. Stale graph error fields cleared after successful retry
# ---------------------------------------------------------------------------

class TestStaleGraphErrorClearance(FrappeTestCase):
    def setUp(self):
        self.sid = _unique_real_leadgen_id()
        self.queue_name = _make_queue(source_lead_id=self.sid)

    def tearDown(self):
        _cleanup(self.queue_name)

    def test_stale_errors_cleared_after_success(self):
        _set_graph_error_fields(
            self.queue_name, code=100, subcode=33,
            message="Object with ID OLD-ATTEMPT does not exist"
        )
        before = _get_graph_error_fields(self.queue_name)
        if before:
            self.assertIsNotNone(before.get("graph_error_code"))

        good_payload = {
            "id": self.sid,
            "field_data": [{"name": "full_name", "values": ["Test Customer"]}],
        }
        with patch("visa_crm.api.pipeline_stage_services.fetch_lead", return_value=good_payload):
            result = graph_download(self.queue_name)

        self.assertEqual(result["graph_payload"]["id"], self.sid)
        after = _get_graph_error_fields(self.queue_name)
        for field, value in after.items():
            self.assertIsNone(value, f"Stale field {field!r} not cleared; value={value!r}")

    def test_successful_graph_payload_preserved(self):
        good_payload = {
            "id": self.sid,
            "field_data": [{"name": "full_name", "values": ["John Doe"]}],
        }
        with patch("visa_crm.api.pipeline_stage_services.fetch_lead", return_value=good_payload):
            graph_download(self.queue_name)
        stored = frappe.db.get_value("Lead Intake Queue", self.queue_name, "graph_payload")
        self.assertIsNotNone(stored)
        data = json.loads(stored)
        self.assertEqual(data["id"], self.sid)
        self.assertTrue(len(data["field_data"]) > 0)

    def test_stale_errors_not_cleared_before_success(self):
        """Error fields must remain until a successful fetch clears them."""
        _set_graph_error_fields(self.queue_name, code=100, subcode=33, message="Stale error")
        before = _get_graph_error_fields(self.queue_name)
        if not before:
            self.skipTest("graph_error_code field not present on this schema")
        self.assertIsNotNone(before.get("graph_error_code"))

    def test_idempotent_rerun_preserves_cleared_state(self):
        good_payload = {
            "id": self.sid,
            "field_data": [{"name": "full_name", "values": ["John Doe"]}],
        }
        with patch("visa_crm.api.pipeline_stage_services.fetch_lead", return_value=good_payload):
            graph_download(self.queue_name)
        # Second call must reuse the existing payload without hitting fetch_lead.
        with patch("visa_crm.api.pipeline_stage_services.fetch_lead",
                   side_effect=AssertionError("must reuse")):
            r2 = graph_download(self.queue_name)
        self.assertTrue(r2["reused"])
        # Error fields must still be clear.
        after = _get_graph_error_fields(self.queue_name)
        for field, value in after.items():
            self.assertIsNone(value, f"{field!r} should be null after reuse path")


# ---------------------------------------------------------------------------
# 3. Empty reconstructed payload rejected by _graph_payload_from_queue
# ---------------------------------------------------------------------------

class TestEmptyReconstructedPayload(FrappeTestCase):
    def _insert_bare(self, source_lead_id, extra=None):
        doc = frappe.new_doc("Lead Intake Queue")
        doc.source_lead_id = source_lead_id
        doc.status = "Lead Received"
        doc.raw_payload = "{}"
        if extra:
            for k, v in extra.items():
                if doc.meta.has_field(k):
                    setattr(doc, k, v)
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        self._inserted = doc.name
        return frappe.get_doc("Lead Intake Queue", doc.name)

    def tearDown(self):
        if hasattr(self, "_inserted"):
            frappe.db.delete("Lead Intake Stage", {"queue": self._inserted})
            frappe.db.delete("Lead Intake Queue", {"name": self._inserted})
            frappe.db.commit()

    def test_attr_id_only_returns_none(self):
        uid = "ATTR-" + frappe.generate_hash(length=8)
        queue = self._insert_bare(uid)
        self.assertIsNone(_graph_payload_from_queue(queue))

    def test_numeric_id_only_returns_none(self):
        sid = _unique_real_leadgen_id()
        queue = self._insert_bare(sid)
        self.assertIsNone(_graph_payload_from_queue(queue))

    def test_custom_answers_returns_non_none_payload(self):
        sid = _unique_real_leadgen_id()
        queue = self._insert_bare(
            sid,
            {"custom_answers": json.dumps({"full_name": "Ali Hassan", "phone_number": "+971501234567"})}
        )
        result = _graph_payload_from_queue(queue)
        self.assertIsNotNone(result, "custom_answers must produce a reconstructed payload")
        self.assertTrue(len(result.get("field_data", [])) > 0)

    def test_pii_fields_return_non_none_payload(self):
        sid = _unique_real_leadgen_id()
        queue = self._insert_bare(sid, {"customer_name": "Ali Hassan", "phone": "+971501234567"})
        result = _graph_payload_from_queue(queue)
        self.assertIsNotNone(result, "PII fields must produce a reconstructed payload")
        self.assertTrue(len(result.get("field_data", [])) > 0)


# ---------------------------------------------------------------------------
# 5. _hydrate_names() isolation from primary payload
# ---------------------------------------------------------------------------

class TestHydrateNamesIsolation(FrappeTestCase):
    def test_primary_success_survives_hydration_failure(self):
        sid = "1584030679973165"

        def fake_get(url, params=None, timeout=None):
            if sid in url:
                resp = MagicMock()
                resp.status_code = 200
                resp.content = b'{"id":"1584030679973165","field_data":[{"name":"full_name","values":["Test"]}],"campaign_id":"ATTR-bad"}' 
                resp.json.return_value = {
                    "id": sid,
                    "field_data": [{"name": "full_name", "values": ["Test"]}],
                    "campaign_id": "ATTR-bad",
                }
                return resp
            resp = MagicMock()
            resp.status_code = 400
            resp.content = b'{"error":{"code":100,"message":"Not found"}}' 
            resp.json.return_value = {"error": {"code": 100, "message": "Not found"}}
            return resp

        with patch("visa_crm.api.meta_graph.requests.get", side_effect=fake_get):
            with patch("visa_crm.api.meta_graph._access_token", return_value="FAKE-TOKEN"):
                lead = fetch_lead(sid)

        self.assertEqual(lead["id"], sid)
        self.assertTrue(len(lead["field_data"]) > 0)
        # No top-level error from enrichment failures.
        self.assertNotIn("error", lead)

    def test_synthetic_campaign_id_skipped_without_http_call(self):
        from visa_crm.api.meta_graph import _hydrate_names
        lead = {"id": "1584030679973165", "field_data": [], "campaign_id": "ATTR-cada7e2f"}
        with patch("visa_crm.api.meta_graph.requests.get") as mock_get:
            warnings = _hydrate_names(lead, "FAKE-TOKEN")
        mock_get.assert_not_called()
        reasons = [w.get("reason") for w in warnings]
        self.assertIn("synthetic_id_skipped", reasons)

    def test_enrichment_failure_returns_warning_list_not_exception(self):
        from visa_crm.api.meta_graph import _hydrate_names
        # Use a real-looking numeric campaign_id so the lookup is attempted.
        lead = {"id": "1584030679973165", "field_data": [], "campaign_id": "1234567890123"}

        def fail_get(url, params=None, timeout=None):
            resp = MagicMock()
            resp.status_code = 400
            resp.content = b'{"error":{"code":100,"message":"Not found"}}' 
            resp.json.return_value = {"error": {"code": 100, "message": "Not found"}}
            return resp

        with patch("visa_crm.api.meta_graph.requests.get", side_effect=fail_get):
            warnings = _hydrate_names(lead, "FAKE-TOKEN")
        # Primary payload is unchanged.
        self.assertEqual(lead["id"], "1584030679973165")
        # Must return a list of warnings, not raise.
        self.assertIsInstance(warnings, list)
        self.assertTrue(any(w.get("reason") == "lookup_failed" for w in warnings))

    def test_primary_error_still_raises(self):
        """A failure on the PRIMARY leadgen fetch must still raise MetaGraphError."""
        def fail_primary(url, params=None, timeout=None):
            resp = MagicMock()
            resp.status_code = 400
            resp.content = b'{"error":{"code":100,"error_subcode":33,"message":"Not found"}}' 
            resp.json.return_value = {
                "error": {"code": 100, "error_subcode": 33, "message": "Not found"}
            }
            return resp

        with patch("visa_crm.api.meta_graph.requests.get", side_effect=fail_primary):
            with patch("visa_crm.api.meta_graph._access_token", return_value="FAKE-TOKEN"):
                with self.assertRaises(PermanentGraphError):
                    fetch_lead("1728701815047004")


# ---------------------------------------------------------------------------
# Task 4 + 6 + 7. Permanent Graph failure cascade
# ---------------------------------------------------------------------------

class TestPermanentGraphFailureCascade(FrappeTestCase):
    def setUp(self):
        # Bare queue: no PII, no custom_answers.
        sid_bare = "ATTR-cascade-bare-" + frappe.generate_hash(length=6)
        self.queue_bare = _make_queue(source_lead_id=sid_bare, raw_payload="{}")
        frappe.db.set_value(
            "Lead Intake Queue", self.queue_bare,
            {"customer_name": None, "phone": None, "email": None, "custom_answers": None},
            update_modified=False,
        )
        # Queue WITH PII: permanent failure must NOT cascade here.
        sid_pii = "ATTR-cascade-pii-" + frappe.generate_hash(length=6)
        self.queue_pii = _make_queue(
            source_lead_id=sid_pii,
            raw_payload="{}",
            customer_name="Ali Hassan",
            phone="+971501234567",
        )
        frappe.db.commit()

    def tearDown(self):
        _cleanup(self.queue_bare)
        _cleanup(self.queue_pii)

    def _perm_exc(self):
        exc = PermanentGraphError("Object does not exist")
        exc.permanent = True
        exc.request = {}
        exc.response = None
        exc.status_code = 400
        return exc

    def _claim(self, queue_name):
        mock = MagicMock()
        mock.name = f"{queue_name}:GRAPH_DOWNLOAD"
        mock.stage = "GRAPH_DOWNLOAD"
        frappe.db.set_value(
            "Lead Intake Stage", f"{queue_name}:GRAPH_DOWNLOAD",
            {"state": "RUNNING", "attempt_count": 1, "max_attempts": 5, "lease_token": "tok-cascade"},
            update_modified=False,
        )
        frappe.db.commit()
        return mock

    def test_no_evidence_normalize_skipped(self):
        graph_failure(self.queue_bare, self._claim(self.queue_bare), self._perm_exc(), "tb")
        frappe.db.commit()
        state = frappe.db.get_value("Lead Intake Stage", f"{self.queue_bare}:NORMALIZE", "state")
        self.assertEqual(state, "SKIPPED",
                         f"Expected NORMALIZE=SKIPPED, got {state!r}")

    def test_pii_evidence_normalize_not_skipped(self):
        graph_failure(self.queue_pii, self._claim(self.queue_pii), self._perm_exc(), "tb")
        frappe.db.commit()
        state = frappe.db.get_value("Lead Intake Stage", f"{self.queue_pii}:NORMALIZE", "state")
        self.assertNotEqual(state, "SKIPPED",
                            "NORMALIZE must NOT be skipped when PII evidence exists")

    def test_retryable_failure_does_not_cascade(self):
        exc = MetaGraphError("Temporary rate limit")
        exc.permanent = False
        exc.request = {}
        exc.response = None
        exc.status_code = 429
        frappe.db.set_value(
            "Lead Intake Stage", f"{self.queue_bare}:NORMALIZE",
            {"state": "NOT_STARTED", "skip_reason": None}, update_modified=False,
        )
        frappe.db.set_value(
            "Lead Intake Stage", f"{self.queue_bare}:GRAPH_DOWNLOAD",
            {"state": "RUNNING", "attempt_count": 1, "max_attempts": 5, "lease_token": "tok-retry"},
            update_modified=False,
        )
        frappe.db.commit()
        graph_failure(self.queue_bare, self._claim(self.queue_bare), exc, "tb")
        frappe.db.commit()
        state = frappe.db.get_value("Lead Intake Stage", f"{self.queue_bare}:NORMALIZE", "state")
        self.assertNotEqual(state, "SKIPPED",
                            "Retryable Graph failure must not cascade to NORMALIZE")

    def test_no_claim_does_not_crash(self):
        # Must not raise even when claim is None.
        graph_failure(self.queue_bare, None, self._perm_exc(), "tb")
        frappe.db.commit()

    def test_already_running_normalize_not_overridden(self):
        """If NORMALIZE is already RUNNING, the cascade must not interfere."""
        frappe.db.set_value(
            "Lead Intake Stage", f"{self.queue_bare}:NORMALIZE",
            {"state": "RUNNING", "lease_token": "active-lease"}, update_modified=False,
        )
        frappe.db.commit()
        graph_failure(self.queue_bare, self._claim(self.queue_bare), self._perm_exc(), "tb")
        frappe.db.commit()
        state = frappe.db.get_value("Lead Intake Stage", f"{self.queue_bare}:NORMALIZE", "state")
        # The cascade skips only NOT_STARTED/BLOCKED states.
        self.assertNotEqual(state, "SKIPPED",
                            "Cascade must not override an already-RUNNING NORMALIZE stage")
