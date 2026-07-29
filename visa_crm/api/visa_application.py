import frappe
from visa_crm.api.meta_utils import has_doctype, set_if_has

def create_for_lead(lead, customer=None, data=None):
    if not has_doctype("Visa Application"):
        frappe.throw("Visa Application DocType is not installed")
    data = data or {}
    existing = frappe.db.exists("Visa Application", {"lead": lead})
    if existing and not customer and not data:
        return existing
    lead_doc = frappe.get_doc("CRM Lead", lead)
    customer = customer or getattr(lead_doc, "customer360", None) or getattr(lead_doc, "customer_360", None) or getattr(lead_doc, "customer_360_match", None)
    values = {"lead": lead, "customer": customer, "applicant_name": data.get("customer_name") or getattr(lead_doc, "lead_name", None) or getattr(lead_doc, "first_name", None), "visa_type": data.get("visa_type") or getattr(lead_doc, "visa_type", None), "country": data.get("country_interested") or getattr(lead_doc, "country_interested", None), "status": "Draft"}
    if existing:
        doc = frappe.get_doc("Visa Application", existing)
        changed = False
        for field, value in values.items():
            if value is not None and doc.meta.has_field(field) and not doc.get(field):
                doc.set(field, value)
                changed = True
        if changed:
            doc.save(ignore_permissions=True)
    else:
        doc = frappe.new_doc("Visa Application")
        for field, value in values.items():
            set_if_has(doc, field, value)
        doc.insert(ignore_permissions=True)
    if lead_doc.meta.has_field("visa_application") and not lead_doc.get("visa_application"):
        frappe.db.set_value("CRM Lead", lead, "visa_application", doc.name, update_modified=False)
    if customer and has_doctype("Customer") and frappe.get_meta("Customer").has_field("visa_application") and not frappe.db.get_value("Customer", customer, "visa_application"):
        frappe.db.set_value("Customer", customer, "visa_application", doc.name, update_modified=False)
    return doc.name
