import frappe
from visa_crm.api.meta_utils import load_json, meta_debug_log, set_if_has

DEFAULT_SOURCE = "Meta Instant Form"
MAPPED_FIELDS = ("lead_name", "first_name", "last_name", "mobile_no", "email", "notes", "country", "city", "custom_budget", "custom_destination", "custom_travel_month", "custom_passport_status", "custom_visa_type")

def create_crm_lead(data, context=None):
    context = context or {}
    meta_debug_log("lead_creation_start", **context)
    meta_fields = _meta_fields(data)
    frappe.logger("visa_crm.meta").info({"meta_fields_before_create": meta_fields})
    lead = frappe.new_doc("CRM Lead")
    name = _lead_name(data, meta_fields)
    source = data.get("lead_source") or data.get("source") or DEFAULT_SOURCE
    _ensure_link_master(lead, "source", source)
    _ensure_link_master(lead, "lead_source", source)
    _ensure_link_master(lead, "status", "Open")
    values = _lead_values(data, meta_fields, name, source)
    for field, value in values.items():
        _set_empty_if_allowed(lead, field, value)
    for field in MAPPED_FIELDS:
        if values.get(field) is not None and lead.meta.has_field(field):
            lead.set(field, values[field])
    _fill_required_text(lead, name)
    before = {field: lead.get(field) for field in MAPPED_FIELDS if lead.meta.has_field(field)}
    frappe.logger("visa_crm.meta").info({"lead_document_before_insert": lead.as_dict()})
    lead.insert(ignore_permissions=True)
    lead.reload()
    after = {field: lead.get(field) for field in MAPPED_FIELDS if lead.meta.has_field(field)}
    frappe.logger("visa_crm.meta").info({"lead_document_after_insert": lead.as_dict()})
    changed = {field: {"before": value, "after": after.get(field)} for field, value in before.items() if value != after.get(field)}
    if changed:
        frappe.logger("visa_crm.meta").warning({"lead_fields_changed_during_insert": changed, "lead": lead.name})
    meta_debug_log("lead_creation_end", lead=lead.name, source=source, **context)
    return lead.name

def _lead_values(data, meta_fields, name, source):
    first_name = _clean_text(data.get("first_name")) or _clean_text(meta_fields.get("full_name")) or name
    phone = data.get("phone") or meta_fields.get("phone") or meta_fields.get("phone_number")
    email = data.get("email") or meta_fields.get("email")
    notes = data.get("notes") or data.get("message") or meta_fields.get("notes") or meta_fields.get("message")
    country = data.get("country") or data.get("country_interested") or meta_fields.get("country")
    visa_type = data.get("custom_visa_type") or data.get("visa_type") or meta_fields.get("visa_type")
    return {"lead_name": name, "first_name": first_name, "last_name": data.get("last_name") or meta_fields.get("last_name"), "customer_name": name, "organization": name, "mobile_no": phone, "phone": phone, "phone_number": phone, "email": email, "email_id": email, "city": data.get("city") or meta_fields.get("city"), "country": country, "country_interested": country, "country_of_interest": country, "visa_type": visa_type, "custom_visa_type": visa_type, "budget": data.get("budget"), "custom_budget": data.get("custom_budget") or data.get("budget"), "travel_date": data.get("travel_date"), "travel_month": data.get("travel_month"), "custom_travel_month": data.get("custom_travel_month") or data.get("travel_month"), "destination": data.get("destination"), "custom_destination": data.get("custom_destination") or data.get("destination"), "passport": data.get("passport"), "custom_passport_status": data.get("custom_passport_status") or data.get("passport"), "message": data.get("message"), "notes": notes, "meta_raw_fields": data.get("meta_raw_fields"), "source": source, "lead_source": source, "status": "Open", "workflow_state": "Lead", "campaign_name": data.get("campaign_name"), "ad_name": data.get("ad_name"), "source_lead_id": data.get("source_lead_id")}

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

def _lead_name(data, meta_fields=None):
    meta_fields = meta_fields or _meta_fields(data)
    name = _clean_text(meta_fields.get("full_name")) or _clean_text(data.get("customer_name")) or _clean_text(data.get("name"))
    return name or f"Meta Lead {data.get('source_lead_id') or ''}".strip()

def _clean_text(value):
    text = str(value or "").strip()
    return text or None

def _meta_fields(data):
    fields = data.get("meta_fields") or data.get("custom_answers") or {}
    return load_json(fields, {}) if isinstance(fields, str) else fields

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
