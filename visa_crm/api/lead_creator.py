import inspect
import frappe
from visa_crm.api.meta_utils import load_json, meta_debug_log, safe_json_dumps

DEFAULT_SOURCE = "Meta Instant Form"
MAPPED_FIELDS = ("lead_name", "first_name", "last_name", "mobile_no", "email", "notes", "country", "city", "custom_budget", "custom_destination", "custom_travel_month", "custom_passport_status", "custom_visa_type")
TRACE_FIELDS = ("first_name", "lead_name", "last_name", "mobile_no", "phone", "email", "status", "source", "facebook_lead_id", "facebook_form_id", "campaign_name", "visa_type", "custom_visa_type", "destination", "custom_destination", "budget", "custom_budget", "custom_travel_month", "custom_passport_status", "country", "country_interested", "meta_raw_fields")

def create_crm_lead(data, context=None):
    context = context or {}
    meta_debug_log("lead_creation_start", **context)
    _log_values("create_crm_lead_start", data, context)
    meta_fields = _meta_fields(data)
    frappe.logger("visa_crm.meta").info({"meta_fields_before_create": meta_fields})
    lead = frappe.new_doc("CRM Lead")
    _set_flag(lead, "visa_crm_pipeline_context", context)
    _trace("after_construction", lead, meta_fields=meta_fields)
    name = _lead_name(data, meta_fields)
    source = data.get("lead_source") or data.get("source") or DEFAULT_SOURCE
    _ensure_link_master(lead, "source", source)
    _ensure_link_master(lead, "lead_source", source)
    _ensure_link_master(lead, "status", "Open")
    _log_values("before_lead_values", {"data": data, "meta_fields": meta_fields, "name": name, "source": source}, context)
    mapped_fields = _lead_values(data, meta_fields, name, source)
    _log_values("after_lead_values", mapped_fields, context)
    _trace("after_lead_values", lead, mapped_fields=mapped_fields)
    _log_values("before_crm_values", mapped_fields, context)
    values = _crm_values(mapped_fields)
    _log_values("after_crm_values", values, context)
    _trace("after_crm_values", lead, mapped_fields=values)
    for field, value in values.items():
        _set_empty_if_allowed(lead, field, value)
    _trace("after_set_empty_if_allowed", lead, mapped_fields=values)
    for field in MAPPED_FIELDS:
        if values.get(field) is not None and lead.meta.has_field(field):
            _set_traced(lead, field, values[field])
    _trace("after_lead_set", lead, mapped_fields=values)
    _fill_required_text(lead, name)
    before = {field: lead.get(field) for field in MAPPED_FIELDS if lead.meta.has_field(field)}
    frappe.logger("visa_crm.meta").info({"crm_lead_field_metadata": _field_metadata(lead)})
    frappe.logger("visa_crm.meta").info({"lead_document_before_insert": lead.as_dict()})
    _trace("before_insert", lead, mapped_fields=values)
    try:
        lead.insert(ignore_permissions=True)
    except Exception as exc:
        traceback = frappe.get_traceback()
        failure = {"traceback": traceback, "lead_document": lead.as_dict(), "meta_fields": meta_fields, "mapped_fields": values, "flags": dict(lead.flags), "validation_message": str(exc), "doctype": lead.doctype, "validator": _validator(exc), "phone_fields": {field: lead.get(field) for field in ("mobile_no", "phone", "phone_number") if lead.meta.has_field(field)}}
        frappe.logger("visa_crm.meta").error({"crm_lead_insert_failure": failure})
        message = safe_json_dumps(failure)
        frappe.log_error(title="CRM Lead Insert Failure", message=message)
        frappe.db.after_rollback.add(lambda: frappe.log_error(title="CRM Lead Insert Failure", message=message))
        raise
    _trace("after_insert", lead, mapped_fields=values)
    lead.reload()
    _trace("after_reload", lead, mapped_fields=values)
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
    return {"lead_name": name, "first_name": first_name, "last_name": data.get("last_name") or meta_fields.get("last_name"), "customer_name": name, "organization": name, "mobile_no": phone, "phone": phone, "phone_number": phone, "email": email, "email_id": email, "city": data.get("city") or meta_fields.get("city"), "country": country, "country_interested": country, "country_of_interest": country, "visa_type": visa_type, "custom_visa_type": visa_type, "budget": data.get("budget"), "custom_budget": data.get("custom_budget") or data.get("budget"), "travel_date": data.get("travel_date"), "travel_month": data.get("travel_month"), "custom_travel_month": data.get("custom_travel_month") or data.get("travel_month"), "destination": data.get("destination"), "custom_destination": data.get("custom_destination") or data.get("destination"), "passport": data.get("passport"), "custom_passport_status": data.get("custom_passport_status") or data.get("passport"), "message": data.get("message"), "notes": notes, "meta_raw_fields": data.get("meta_raw_fields"), "source": source, "lead_source": source, "status": "Open", "workflow_state": "Lead", "campaign_name": data.get("campaign_name"), "ad_name": data.get("ad_name"), "facebook_lead_id": data.get("source_lead_id"), "facebook_form_id": data.get("form_id")}

def _set_empty_if_allowed(doc, field, value):
    if not value or not doc.meta.has_field(field) or doc.get(field) or not _allowed(doc, field, value):
        return
    _set_traced(doc, field, value)

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
    return None if _is_meta_test_placeholder(text) else text or None

def _meta_fields(data):
    fields = data.get("meta_fields") or data.get("custom_answers") or {}
    return load_json(fields, {}) if isinstance(fields, str) else fields

def _fill_required_text(doc, value):
    for field in doc.meta.get("fields"):
        if field.reqd and field.fieldtype in ("Data", "Small Text", "Text") and not doc.get(field.fieldname):
            _set_traced(doc, field.fieldname, value)

def _field_metadata(doc):
    fields = {}
    for fieldname in ("first_name", "lead_name", "last_name", "full_name"):
        field = doc.meta.get_field(fieldname)
        if field:
            fields[fieldname] = {"reqd": field.reqd, "mandatory_depends_on": field.mandatory_depends_on, "default": field.default}
    return fields

def _crm_values(values):
    return {field: value if field == "meta_raw_fields" or not _is_meta_test_placeholder(value) else None for field, value in values.items()}

def _is_meta_test_placeholder(value):
    text = str(value or "").strip().lower()
    return text.startswith("<test lead: dummy data for ") and text.endswith(">")

def _validator(exc):
    return "frappe.utils.validate_phone_number" if isinstance(exc, frappe.InvalidPhoneNumberError) else exc.__class__.__name__

def log_crm_lead_hook(doc, method=None):
    if not (getattr(doc, "source_lead_id", None) or getattr(doc, "source", None) == DEFAULT_SOURCE):
        return
    current = {field: doc.get(field) for field in MAPPED_FIELDS if doc.meta.has_field(field)}
    previous = getattr(doc.flags, "visa_crm_meta_trace_fields", {}) or {}
    changes = {field: {"old": previous.get(field), "new": value} for field, value in current.items() if previous.get(field) != value}
    frappe.logger("visa_crm.meta").info({"crm_lead_stage": f"hook_{method}", "crm_lead_hook": method, "field_changes": changes, "lead_document": doc.as_dict()})
    doc.flags.visa_crm_meta_trace_fields = current
    _trace(f"hook_{method}", doc, controller=_controller_source(doc, method))

def _trace(stage, doc, **data):
    frappe.logger("visa_crm.meta").info({"crm_lead_stage": stage, "lead_document": doc.as_dict(), **data})
    current = {field: doc.get(field) for field in TRACE_FIELDS if doc.meta.has_field(field)}
    previous = _get_flag(doc, "visa_crm_pipeline_trace_fields")
    source = data.get("controller") or _location()
    changes = {}
    if previous is not None:
        for field, value in current.items():
            if previous.get(field) != value:
                changes[field] = {"old": _typed(previous.get(field)), "new": _typed(value), **source}
    payload = {"event": "crm_lead_lifecycle", "stage": stage, "context": _get_flag(doc, "visa_crm_pipeline_context", {}) or {}, "fields": {field: _typed(value) for field, value in current.items()}, "changes": changes, "document": doc.as_dict(), "source": source, "data": data}
    _pipeline_logger().info(safe_json_dumps(payload))
    _set_flag(doc, "visa_crm_pipeline_trace_fields", current)

def _set_traced(doc, field, value):
    source = _location()
    old = doc.get(field)
    _pipeline_logger().info(safe_json_dumps({"event": "crm_lead_set_before", "field": field, "old": _typed(old), "candidate": _typed(value), "source": source, "context": _get_flag(doc, "visa_crm_pipeline_context", {}) or {}}))
    doc.set(field, value)
    new = doc.get(field)
    _pipeline_logger().info(safe_json_dumps({"event": "crm_lead_set_after", "field": field, "old": _typed(old), "new": _typed(new), "changed": old != new, "source": source, "context": _get_flag(doc, "visa_crm_pipeline_context", {}) or {}}))

def _log_values(stage, values, context=None):
    _pipeline_logger().info(safe_json_dumps({"event": stage, "context": context or {}, "values": _typed_mapping(values)}))

def _typed_mapping(values):
    if not isinstance(values, dict):
        return _typed(values)
    return {key: _typed_mapping(value) if isinstance(value, dict) else _typed(value) for key, value in values.items()}

def _typed(value):
    return {"value": value, "type": f"{type(value).__module__}.{type(value).__qualname__}", "repr": repr(value)}

def _location():
    frame = inspect.currentframe().f_back.f_back
    return {"function": frame.f_code.co_name, "file": frame.f_code.co_filename, "line": frame.f_lineno}

def _controller_source(doc, method):
    function = getattr(type(doc), method or "", None)
    if function:
        try:
            return {"function": f"{type(doc).__module__}.{type(doc).__qualname__}.{method}", "file": inspect.getsourcefile(function), "line": inspect.getsourcelines(function)[1]}
        except (OSError, TypeError):
            pass
    if method == "autoname":
        return {"function": "frappe.model.naming.set_new_name", "file": "frappe/model/naming.py", "line": 172}
    return _location()

def _get_flag(doc, key, default=None):
    flags = getattr(doc, "flags", {})
    return flags.get(key, default) if isinstance(flags, dict) else getattr(flags, key, default)

def _set_flag(doc, key, value):
    flags = getattr(doc, "flags", {})
    flags[key] = value

def _pipeline_logger():
    logger = frappe.logger("visa_crm.pipeline")
    logger.setLevel("INFO")
    return logger

def _allowed(doc, field, value):
    meta_field = doc.meta.get_field(field)
    if not value or not meta_field:
        return False
    if meta_field.fieldtype != "Select" or not meta_field.options:
        return True
    return value in [option.strip() for option in meta_field.options.split("\n") if option.strip()]
