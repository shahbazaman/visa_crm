import frappe
from frappe.model.document import Document
import re

VISA_SUFFIX_PATTERN = re.compile(r"(?i)(?:^|[\s_\-]+)visa\s*$")


def is_visa_suffix(name):
    if not name:
        return False
    return bool(VISA_SUFFIX_PATTERN.search(str(name).strip()))


class LeadSubcategory(Document):
    def validate(self):
        if not self.sub_category_name or not str(self.sub_category_name).strip():
            frappe.throw("Sub-category Name is required", frappe.ValidationError)

        # MANDATORY RULE: Any category or subcategory name whose normalized name ends
        # with the word 'visa' must belong under the Global Visa parent category.
        if is_visa_suffix(self.sub_category_name):
            if self.parent_category != "Global Visa":
                if frappe.db.exists("Lead Category", "Global Visa"):
                    self.parent_category = "Global Visa"
                else:
                    frappe.throw(
                        "Subcategory ending with 'visa' must belong to parent category 'Global Visa'",
                        frappe.ValidationError,
                    )

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
