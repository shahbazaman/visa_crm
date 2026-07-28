import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIELDS = [
    ("city", "City", "Data", None),
    ("notes", "Notes", "Long Text", None),
    ("meta_raw_fields", "Meta Raw Fields", "Long Text", None),
    ("custom_budget", "Budget", "Data", None),
    ("custom_travel_month", "Travel Month", "Data", None),
    ("custom_destination", "Destination", "Data", None),
    ("custom_passport_status", "Passport Status", "Data", None),
    ("custom_visa_type", "Visa Type", "Data", None)
]

def execute():
    if not frappe.db.exists("DocType", "CRM Lead"):
        return
    meta = frappe.get_meta("CRM Lead")
    rows = []
    for fieldname, label, fieldtype, options in FIELDS:
        if not meta.has_field(fieldname):
            rows.append({"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "options": options, "insert_after": _insert_after(meta)})
    if rows:
        create_custom_fields({"CRM Lead": rows}, update=True)
    frappe.db.commit()

def _insert_after(meta):
    for field in ("source_lead_id", "visa_type", "country_interested", "email", "email_id"):
        if meta.has_field(field):
            return field
    return None
