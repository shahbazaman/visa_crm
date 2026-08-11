import frappe
from frappe.model.document import Document


class LeadSubcategory(Document):
    def validate(self):
        if not self.sub_category_name or not str(self.sub_category_name).strip():
            frappe.throw("Sub-category Name is required", frappe.ValidationError)
        if not self.parent_category or not frappe.db.exists("Lead Category", self.parent_category):
            frappe.throw("Valid Parent Category is required", frappe.ValidationError)

        existing = frappe.db.exists(
            "Lead Subcategory",
            {
                "sub_category_name": str(self.sub_category_name).strip(),
                "parent_category": self.parent_category,
                "name": ["!=", self.name],
            },
        )
        if existing:
            frappe.throw(
                f"Sub-category '{self.sub_category_name}' already exists under category '{self.parent_category}'",
                frappe.DuplicateEntryError,
            )
