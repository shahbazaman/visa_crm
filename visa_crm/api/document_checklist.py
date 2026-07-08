import frappe
from visa_crm.api.meta_utils import has_doctype, set_if_has

DEFAULT_DOCUMENTS = {
    "default": ["Passport", "Photo", "Bank Statement", "Travel History"],
    "Student": ["Passport", "Photo", "Academic Records", "Bank Statement", "Offer Letter"],
    "Work": ["Passport", "Photo", "Experience Letter", "Employment Contract", "Bank Statement"],
    "Visit": ["Passport", "Photo", "Invitation Letter", "Bank Statement", "Travel Itinerary"]
}

def generate_checklist(lead, visa_type=None, country=None):
    if not has_doctype("Customer Documents"):
        return []
    lead_doc = frappe.get_doc("CRM Lead", lead)
    visa_type = visa_type or getattr(lead_doc, "visa_type", None) or "default"
    docs = _documents(visa_type, country or getattr(lead_doc, "country_interested", None))
    created = []
    for item in docs:
        if frappe.db.exists("Customer Documents", {"lead": lead, "document_type": item}):
            continue
        doc = frappe.new_doc("Customer Documents")
        for field, value in {"lead": lead, "document_type": item, "status": "Pending", "visa_type": visa_type, "country": country}.items():
            set_if_has(doc, field, value)
        doc.insert(ignore_permissions=True)
        created.append(doc.name)
    return created

def _documents(visa_type, country=None):
    rules = frappe.conf.get("visa_crm_document_checklists") or {}
    key = f"{country}:{visa_type}" if country else visa_type
    return rules.get(key) or rules.get(visa_type) or DEFAULT_DOCUMENTS.get(visa_type) or DEFAULT_DOCUMENTS["default"]
