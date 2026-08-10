import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api.customer360 import resolve_customer, resolve_lead, _claim_identities, _link_lead_customer
from visa_crm.api.pipeline_stage_services import customer360, crm_lead
from visa_crm.api.pipeline_engine import ensure_stage_ledger, run_stage
from visa_crm.api.recovery import retry_queue

class TestCustomer360Resilience(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.test_phone = "+19998887766"
        self.test_email = "resilience.test@example.com"
        self.test_lead_id = f"RESILIENCE-META-{frappe.generate_hash(length=8)}"

    def test_identity_collision_does_not_crash_customer360(self):
        # Create Customer A
        cust_a = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": "Test Customer A",
            "customer_type": "Individual",
            "customer_group": "Individual",
            "mobile_no": self.test_phone,
            "email_id": self.test_email
        })
        cust_a.insert(ignore_permissions=True)
        frappe.db.commit()

        # Claim identity for Customer A
        _claim_identities(cust_a.name, {"phone": self.test_phone, "email": self.test_email})

        # Create Customer B
        cust_b = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": "Test Customer B",
            "customer_type": "Individual",
            "customer_group": "Individual",
            "mobile_no": "+19998887777"
        })
        cust_b.insert(ignore_permissions=True)
        frappe.db.commit()

        # Attempt to claim the same phone identity for Customer B. Should NOT throw ValidationError.
        try:
            _claim_identities(cust_b.name, {"phone": self.test_phone})
        except Exception as exc:
            self.fail(f"_claim_identities threw unexpected exception on identity conflict: {exc}")

    def test_last_error_persists_on_queue_failure(self):
        # Create a test Lead Intake Queue
        lead_id = f"ERR-TEST-LEAD-{frappe.generate_hash(length=8)}"
        queue = frappe.get_doc({
            "doctype": "Lead Intake Queue",
            "status": "Lead Received",
            "lead_source": "Meta Instant Form",
            "source_lead_id": lead_id
        })
        queue.insert(ignore_permissions=True)
        frappe.db.commit()

        ensure_stage_ledger(queue.name)

        # Complete dependencies so CUSTOMER360 can be claimed
        for dep_stage in ("WEBHOOK", "GRAPH_DOWNLOAD", "NORMALIZE", "CLASSIFICATION"):
            frappe.db.set_value("Lead Intake Stage", f"{queue.name}:{dep_stage}", {"state": "COMPLETED"}, update_modified=False)

        def failing_handler(qname, claim):
            raise ValueError("Test forced pipeline failure message")

        outcome = run_stage(queue.name, failing_handler, stage="CUSTOMER360")
        self.assertIsNotNone(outcome)
        self.assertFalse(outcome.ok)

        # Verify last_error on Lead Intake Queue is populated
        last_err = frappe.db.get_value("Lead Intake Queue", queue.name, "last_error")
        self.assertIsNotNone(last_err)
        self.assertIn("Test forced pipeline failure message", last_err)

    def test_idempotent_customer360_resolution_and_retry_queue(self):
        lead_id = f"IDEM-LEAD-{frappe.generate_hash(length=8)}"
        queue = frappe.get_doc({
            "doctype": "Lead Intake Queue",
            "status": "Lead Downloaded",
            "lead_source": "Meta Instant Form",
            "source_lead_id": lead_id,
            "customer_name": "Idempotent User",
            "phone": "+18887776655",
            "email": "idempotent@example.com",
            "normalized_payload": frappe.as_json({"source_lead_id": lead_id, "customer_name": "Idempotent User", "phone": "+18887776655", "email": "idempotent@example.com"}),
            "normalized_payload_hash": "hash_123"
        })
        queue.insert(ignore_permissions=True)
        frappe.db.commit()

        ensure_stage_ledger(queue.name)
        for dep_stage in ("WEBHOOK", "GRAPH_DOWNLOAD", "NORMALIZE", "CLASSIFICATION"):
            frappe.db.set_value("Lead Intake Stage", f"{queue.name}:{dep_stage}", {"state": "COMPLETED"}, update_modified=False)

        # Execute retry_queue as System Manager
        frappe.set_user("Administrator")
        res = retry_queue(queue.name)
        self.assertTrue(res.get("ok") or res.get("status") in ("Processed", "Lead Created", "Customer Matched"))
        self.assertIsNotNone(res.get("matched_customer"))

    def test_conflicting_phone_and_email_identities(self):
        phone_cust = "+17776665544"
        email_cust = "conflict.user@example.com"

        cust_p = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": "Customer Phone Only",
            "customer_type": "Individual",
            "customer_group": "Individual",
            "mobile_no": phone_cust
        })
        cust_p.insert(ignore_permissions=True)

        cust_e = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": "Customer Email Only",
            "customer_type": "Individual",
            "customer_group": "Individual",
            "email_id": email_cust
        })
        cust_e.insert(ignore_permissions=True)
        frappe.db.commit()

        _claim_identities(cust_p.name, {"phone": phone_cust})
        _claim_identities(cust_e.name, {"email": email_cust})

        # When resolving data containing BOTH phone_cust and email_cust:
        data = {"phone": phone_cust, "email": email_cust, "source_lead_id": "CONFLICT-LEAD-001"}
        resolved = resolve_customer(data)
        # Primary identity match should resolve to one of the customers without throwing ValidationError
        self.assertIn(resolved, (cust_p.name, cust_e.name))
