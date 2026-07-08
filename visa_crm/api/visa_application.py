import frappe
from visa_crm.api.meta_utils import has_doctype, set_if_has

def create_for_lead(lead):
    if not has_doctype("Visa Application"):
        frappe.throw("Visa Application DocType is not installed")
    existing = frappe.db.exists("Visa Application", {"lead": lead})
    if existing:
        return existing
    lead_doc = frappe.get_doc("CRM Lead", lead)
    doc = frappe.new_doc("Visa Application")
    for field, value in {"lead": lead, "customer": getattr(lead_doc, "customer", None), "applicant_name": getattr(lead_doc, "lead_name", None) or getattr(lead_doc, "first_name", None), "visa_type": getattr(lead_doc, "visa_type", None), "country": getattr(lead_doc, "country_interested", None), "status": "Draft"}.items():
        set_if_has(doc, field, value)
    doc.insert(ignore_permissions=True)
    return doc.name
