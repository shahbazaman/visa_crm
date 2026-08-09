import unittest
import frappe
from visa_crm.api.customer import create_customer

class TestCustomerSanitization(unittest.TestCase):
    def test_customer_name_sanitization(self):
        raw_name = "<test lead: dummy data for full_name>"
        name = create_customer({
            "customer_name": raw_name,
            "source_lead_id": "861435083391720"
        })
        self.assertIsNotNone(name)
        self.assertNotIn("<", name)
        self.assertNotIn(">", name)
        # Cleanup
        frappe.delete_doc("Customer", name, force=True)
