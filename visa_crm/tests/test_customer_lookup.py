import unittest
from unittest.mock import call,patch
from visa_crm.api import customer

class TestCustomerLookup(unittest.TestCase):
    def test_phone_lookup_uses_customer_phone_fields(self):
        phone="+971500000001"
        with patch.object(customer,"has_field",return_value=True),patch.object(customer.frappe.db,"get_value",side_effect=[None,"CUST-1"]) as get_value:
            result=customer.find_customer(phone=phone)
        self.assertEqual(result,"CUST-1")
        self.assertEqual(get_value.call_args_list,[call("Customer",{"mobile_no":phone},"name"),call("Customer",{"whatsapp_no":phone},"name")])
