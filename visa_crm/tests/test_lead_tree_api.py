import unittest
import frappe
from visa_crm.api.lead_tree import get_lead_tree_nodes, _build_orm_filters

class TestLeadTreeAPI(unittest.TestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_categories_returns_list(self):
        nodes = get_lead_tree_nodes(parent_level="Categories")
        self.assertIsInstance(nodes, list)
        if nodes:
            first = nodes[0]
            self.assertIn("value", first)
            self.assertIn("label", first)
            self.assertIn("count", first)
            self.assertIn("expandable", first)

    def test_uncategorized_subcategories_returns_list(self):
        nodes = get_lead_tree_nodes(parent_level="Subcategories", category="Uncategorized")
        self.assertIsInstance(nodes, list)
        if nodes:
            first = nodes[0]
            self.assertIn("value", first)
            self.assertIn("count", first)

    def test_uncategorized_no_subcategory_leads(self):
        res = get_lead_tree_nodes(parent_level="Leads", category="Uncategorized", subcategory="No Subcategory")
        self.assertIsInstance(res, dict)
        self.assertIn("data", res)
        self.assertIn("has_more", res)

    def test_orm_filters_uncategorized(self):
        or_filters, orm_filters = _build_orm_filters({}, category="Uncategorized", subcategory="No Subcategory")
        cat_filter = [f for f in orm_filters if "lead_category" in f[1]]
        sub_filter = [f for f in orm_filters if "lead_group" in f[1]]
        self.assertTrue(len(cat_filter) > 0)
        self.assertTrue(len(sub_filter) > 0)
        self.assertEqual(cat_filter[0][2], "in")
        self.assertEqual(sub_filter[0][2], "in")

    def test_orm_filters_specific_category(self):
        or_filters, orm_filters = _build_orm_filters({}, category="Student Visa", subcategory="General")
        cat_filter = [f for f in orm_filters if f[1] == "lead_category"]
        sub_filter = [f for f in orm_filters if f[1] == "lead_group"]
        self.assertEqual(cat_filter[0][3], "Student Visa")
        self.assertEqual(sub_filter[0][3], "General")
