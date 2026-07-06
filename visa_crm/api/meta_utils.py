import json
import re
import frappe
from frappe.utils import cint, now

MAX_RETRIES = 5

def get_meta_settings():
    name = frappe.get_all("Meta Settings", pluck="name", limit=1)
    return frappe.get_doc("Meta Settings", name[0]) if name else None

def safe_json_dumps(value):
    return json.dumps(value, default=str, ensure_ascii=False, separators=(",", ":"))

def load_json(value, default=None):
    if not value:
        return default if default is not None else {}
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default if default is not None else {}

def has_doctype(doctype):
    return frappe.db.exists("DocType", doctype)

def has_field(doctype, fieldname):
    return frappe.get_meta(doctype).has_field(fieldname) if has_doctype(doctype) else False

def set_if_has(doc, fieldname, value):
    if value is not None and doc.meta.has_field(fieldname):
        doc.set(fieldname, value)

def set_values(doctype, name, values, update_modified=False):
    clean = {field: value for field, value in values.items() if has_field(doctype, field)}
    if clean:
        frappe.db.set_value(doctype, name, clean, update_modified=update_modified)

def queue_status(name, status, **values):
    source_lead_id = values.get("source_lead_id") or frappe.db.get_value("Lead Intake Queue", name, "source_lead_id")
    meta_debug_log("queue_status_update_start", queue_name=name, source_lead_id=source_lead_id, status=status)
    values.update({"status": status})
    set_values("Lead Intake Queue", name, values)
    meta_debug_log("queue_status_update_end", queue_name=name, source_lead_id=source_lead_id, status=status)

def retry_count(doc):
    return cint(getattr(doc, "retry_count", 0) or 0)

def normalize_phone(value):
    if not value:
        return None
    cleaned = re.sub(r"[^\d+]", "", str(value))
    return cleaned or None

def log_info(event, **data):
    message = safe_json_dumps({"event": event, "data": data, "ts": now()})
    frappe.logger("visa_crm.meta").info(message)

def log_exception(event, **data):
    data["traceback"] = frappe.get_traceback()
    frappe.logger("visa_crm.meta").error(safe_json_dumps({"event": event, "data": data, "ts": now()}))

def meta_context(queue_name=None, source_lead_id=None, status=None):
    return {"queue_name": queue_name, "source_lead_id": source_lead_id, "status": status}

def meta_debug_log(event, queue_name=None, source_lead_id=None, status=None, **data):
    payload = {"event": event, "queue_name": queue_name, "source_lead_id": source_lead_id, "status": status, "traceback": data.pop("traceback", "") or "", "data": data, "ts": now()}
    frappe.log_error(title=f"Meta Lead Debug: {event}", message=safe_json_dumps(payload))
