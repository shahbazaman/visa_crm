import frappe
from visa_crm.api.meta_utils import meta_debug_log, set_if_has

DEFAULT_SOURCE = "Meta Instant Form"

def create_crm_lead(data, context=None):
    context = context or {}
    meta_debug_log("lead_creation_start", **context)
    doc = frappe.new_doc("CRM Lead")
    name = data.get("customer_name") or "Meta Lead"
    source = data.get("lead_source") or data.get("source") or DEFAULT_SOURCE
    _ensure_link_master(doc, "source", source)
    _ensure_link_master(doc, "lead_source", source)
    for field in ("lead_name", "first_name", "customer_name", "organization"):
        set_if_has(doc, field, name)
    for field in ("mobile_no", "phone", "phone_number"):
        set_if_has(doc, field, data.get("phone"))
    for field in ("email", "email_id"):
        set_if_has(doc, field, data.get("email"))
    for field, value in {"source": source, "lead_source": source, "status": "Open", "workflow_state": "Lead", "country_of_interest": data.get("country_interested"), "country_interested": data.get("country_interested"), "visa_type": data.get("visa_type"), "campaign_name": data.get("campaign_name"), "ad_name": data.get("ad_name"), "source_lead_id": data.get("source_lead_id")}.items():
        if _allowed(doc, field, value):
            set_if_has(doc, field, value)
    doc.insert(ignore_permissions=True)
    meta_debug_log("lead_creation_end", lead=doc.name, source=source, **context)
    return doc.name

def _ensure_link_master(doc, fieldname, value):
    field = doc.meta.get_field(fieldname)
    if not value or not field or field.fieldtype != "Link" or not field.options:
        return
    if frappe.db.exists(field.options, value):
        return
    try:
        master = frappe.new_doc(field.options)
        master.name = value
        _set_title(master, value)
        master.insert(ignore_permissions=True, ignore_if_duplicate=True)
    except frappe.DuplicateEntryError:
        return

def _set_title(doc, value):
    for field in (doc.meta.title_field, "source_name", "lead_source", "source", "title"):
        if field and doc.meta.has_field(field):
            doc.set(field, value)
            return

def _allowed(doc, field, value):
    meta_field = doc.meta.get_field(field)
    if not value or not meta_field:
        return False
    if meta_field.fieldtype != "Select" or not meta_field.options:
        return True
    return value in [option.strip() for option in meta_field.options.split("\n") if option.strip()]
