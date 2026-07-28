import frappe
from visa_crm.api.meta_utils import meta_debug_log, set_if_has

DEFAULT_SOURCE = "Meta Instant Form"

def create_crm_lead(data, context=None):
    context = context or {}
    meta_debug_log("lead_creation_start", **context)
    doc = frappe.new_doc("CRM Lead")
    name = _lead_name(data)
    source = data.get("lead_source") or data.get("source") or DEFAULT_SOURCE
    _ensure_link_master(doc, "source", source)
    _ensure_link_master(doc, "lead_source", source)
    _ensure_link_master(doc, "status", "Open")
    values = _lead_values(data, name, source)
    for field, value in values.items():
        _set_empty_if_allowed(doc, field, value)
    _fill_required_text(doc, name)
    doc.insert(ignore_permissions=True)
    meta_debug_log("lead_creation_end", lead=doc.name, source=source, **context)
    return doc.name

def _lead_values(data, name, source):
    first_name = _clean_text(data.get("first_name")) or name
    notes = data.get("notes") or data.get("message")
    country = data.get("country") or data.get("country_interested")
    visa_type = data.get("custom_visa_type") or data.get("visa_type")
    return {"lead_name": name, "first_name": first_name, "last_name": data.get("last_name"), "customer_name": name, "organization": name, "mobile_no": data.get("phone"), "phone": data.get("phone"), "phone_number": data.get("phone"), "email": data.get("email"), "email_id": data.get("email"), "city": data.get("city"), "country": country, "country_interested": country, "country_of_interest": country, "visa_type": visa_type, "custom_visa_type": visa_type, "budget": data.get("budget"), "custom_budget": data.get("custom_budget") or data.get("budget"), "travel_date": data.get("travel_date"), "travel_month": data.get("travel_month"), "custom_travel_month": data.get("custom_travel_month") or data.get("travel_month"), "destination": data.get("destination"), "custom_destination": data.get("custom_destination") or data.get("destination"), "passport": data.get("passport"), "custom_passport_status": data.get("custom_passport_status") or data.get("passport"), "message": data.get("message"), "notes": notes, "meta_raw_fields": data.get("meta_raw_fields"), "source": source, "lead_source": source, "status": "Open", "workflow_state": "Lead", "campaign_name": data.get("campaign_name"), "ad_name": data.get("ad_name"), "source_lead_id": data.get("source_lead_id")}

def _set_empty_if_allowed(doc, field, value):
    if not value or not doc.meta.has_field(field) or doc.get(field) or not _allowed(doc, field, value):
        return
    set_if_has(doc, field, value)

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
    for field in (doc.meta.title_field, "source_name", "lead_source", "source", "status_name", "status", "label", "title"):
        if field and doc.meta.has_field(field):
            doc.set(field, value)
    for field in doc.meta.get("fields"):
        if field.reqd and field.fieldtype in ("Data", "Small Text") and not doc.get(field.fieldname):
            doc.set(field.fieldname, value)

def _lead_name(data):
    name = _clean_text(data.get("customer_name")) or _clean_text(data.get("name"))
    return name or f"Meta Lead {data.get('source_lead_id') or ''}".strip()

def _clean_text(value):
    text = str(value or "").strip()
    if not text or text.lower().startswith("<test lead:"):
        return None
    return text

def _fill_required_text(doc, value):
    for field in doc.meta.get("fields"):
        if field.reqd and field.fieldtype in ("Data", "Small Text", "Text") and not doc.get(field.fieldname):
            doc.set(field.fieldname, value)

def _allowed(doc, field, value):
    meta_field = doc.meta.get_field(field)
    if not value or not meta_field:
        return False
    if meta_field.fieldtype != "Select" or not meta_field.options:
        return True
    return value in [option.strip() for option in meta_field.options.split("\n") if option.strip()]
