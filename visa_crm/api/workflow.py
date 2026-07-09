import frappe
from visa_crm.api.meta_utils import has_doctype, meta_debug_log, set_if_has

def mark_lead_stage(lead, stage="Lead", context=None):
    context = context or {}
    meta_debug_log("workflow_update_start", lead=lead, stage=stage, **context)
    if not lead or not has_doctype("CRM Lead"):
        meta_debug_log("workflow_update_end", lead=lead, stage=stage, skipped=True, **context)
        return
    doc = frappe.get_doc("CRM Lead", lead)
    for field in ("workflow_state", "stage", "status"):
        if _allowed(doc, field, stage):
            _ensure_link_master(doc, field, stage)
            set_if_has(doc, field, stage)
    doc.save(ignore_permissions=True)
    meta_debug_log("workflow_update_end", lead=lead, stage=stage, **context)

def qualify_lead(lead, context=None):
    mark_lead_stage(lead, "Qualified", context)

def create_deal_if_supported(lead, data=None):
    if not lead or not has_doctype("CRM Deal"):
        return None
    existing = frappe.db.exists("CRM Deal", {"lead": lead}) if frappe.get_meta("CRM Deal").has_field("lead") else None
    if existing:
        return existing
    doc = frappe.new_doc("CRM Deal")
    for field, value in {"lead": lead, "deal_name": (data or {}).get("customer_name") or lead, "status": "Open", "source": "Meta Ads"}.items():
        _ensure_link_master(doc, field, value)
        set_if_has(doc, field, value)
    doc.insert(ignore_permissions=True)
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
        for target in (master.meta.title_field, "status_name", "deal_status", "source_name", "lead_source", "source", "label", "title"):
            if target and master.meta.has_field(target):
                master.set(target, value)
        for target in master.meta.get("fields"):
            if target.reqd and target.fieldtype in ("Data", "Small Text", "Text") and not master.get(target.fieldname):
                master.set(target.fieldname, value)
        master.insert(ignore_permissions=True, ignore_if_duplicate=True)
    except frappe.DuplicateEntryError:
        return

def _allowed(doc, field, value):
    meta_field = doc.meta.get_field(field)
    if not meta_field:
        return False
    if meta_field.fieldtype != "Select" or not meta_field.options:
        return True
    return value in [option.strip() for option in meta_field.options.split("\n") if option.strip()]
