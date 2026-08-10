import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api.customer360 import resolve_customer, resolve_lead, _claim_identities
from visa_crm.api.pipeline_stage_services import customer360, crm_lead
from visa_crm.api.pipeline_engine import ensure_stage_ledger, run_stage

class TestCustomer360Resilience(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.test_phone = "+19998887766"
        self.test_email = "resilience.test@example.com"
        self.test_lead_id = "RESILIENCE-META-LEAD-101"

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
