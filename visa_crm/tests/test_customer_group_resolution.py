import unittest
import frappe
from visa_crm.api.customer import _resolve_customer_group, create_customer

class TestCustomerGroupResolution(unittest.TestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_resolve_customer_group_returns_non_group(self):
        group = _resolve_customer_group()
        self.assertIsNotNone(group)
        is_group = frappe.db.get_value("Customer Group", group, "is_group")
        self.assertEqual(is_group, 0)

    def test_create_customer_sets_valid_customer_group(self):
        test_phone = "+971501234567"
        existing = frappe.db.get_value("Customer", {"mobile_no": test_phone}, "name")
        if existing:
            frappe.delete_doc("Customer", existing, force=True)
        
        name = create_customer({
            "customer_name": "Test Customer Group Lead",
            "phone": test_phone,
            "email": "test_cg@example.com"
        })
        self.assertIsNotNone(name)
        cust_group = frappe.db.get_value("Customer", name, "customer_group")
        self.assertIsNotNone(cust_group)
        is_group = frappe.db.get_value("Customer Group", cust_group, "is_group")
        self.assertEqual(is_group, 0, f"Customer group {cust_group} must be a leaf (is_group=0)")
        
        # Cleanup
        frappe.delete_doc("Customer", name, force=True)
