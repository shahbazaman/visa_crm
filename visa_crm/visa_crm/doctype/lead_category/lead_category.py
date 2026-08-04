import frappe
import re
import unicodedata
from frappe.model.document import Document


class LeadCategory(Document):
    def validate(self):
        self.category_key = _key(self.category_key or self.category_name)
        if self.is_uncategorized:
            self.is_active = 1
            self.allow_all_operational_users = 1


def _key(value):
    value = unicodedata.normalize("NFKC", str(value or "")).casefold().replace("_", " ")
    return re.sub(r"[^\w]+", "-", value, flags=re.UNICODE).strip("-")
