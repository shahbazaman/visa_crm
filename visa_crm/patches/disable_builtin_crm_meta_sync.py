import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CRM_SYNC_METHOD = "crm.lead_syncing.background_sync.sync_leads_from_all_enabled_sources"

def execute():
    _queue_fields()
    result = disable_builtin_meta_sync()
    frappe.logger("visa_crm.meta").info(f"CRM Meta sync audit: {result}")

def disable_builtin_meta_sync():
    custom_active = _custom_pipeline_active()
    result = {"custom_pipeline_active": custom_active, "lead_sync_source": [], "scheduled_job_type": []}
    if not custom_active:
        result["action"] = "skipped_custom_pipeline_not_active"
        return result
    meta_rows, other_enabled = _lead_sync_sources()
    for row in meta_rows:
        changed = _disable_lead_sync_source(row)
        result["lead_sync_source"].append({"name": row.name, "changed": changed})
    if not other_enabled:
        result["scheduled_job_type"] = _disable_scheduled_job()
        result["action"] = "disabled_meta_sources_and_stopped_global_crm_sync_job"
    else:
        result["action"] = "disabled_meta_sources_only_kept_global_crm_sync_for_other_sources"
    frappe.db.commit()
    return result

def _queue_fields():
    if not frappe.db.exists("DocType", "Lead Intake Queue"):
        return
    create_custom_fields({"Lead Intake Queue": [
        {"fieldname": "graph_api_request", "label": "Graph API Request", "fieldtype": "Long Text", "insert_after": "graph_payload"},
        {"fieldname": "graph_api_response", "label": "Graph API Response", "fieldtype": "Long Text", "insert_after": "graph_api_request"}
    ]}, update=True)

def _custom_pipeline_active():
    if not frappe.db.exists("DocType", "Lead Intake Queue"):
        return False
    try:
        import visa_crm.hooks as hooks
        cron = (getattr(hooks, "scheduler_events", {}) or {}).get("cron") or {}
        methods = [method for jobs in cron.values() for method in jobs]
        return "visa_crm.api.intake_processor.process_pending" in methods
    except Exception:
        return False

def _lead_sync_sources():
    if not frappe.db.exists("DocType", "Lead Sync Source"):
        return [], []
    meta = frappe.get_meta("Lead Sync Source")
    fields = ["name"] + [field for field in ("source", "type", "platform", "lead_source", "title", "provider", "enabled", "disabled", "lead_gen_form", "leadgen_form", "lead_gen_form_id", "form_id") if meta.has_field(field)]
    rows = frappe.get_all("Lead Sync Source", fields=fields)
    meta_rows = [row for row in rows if _is_meta_source(row)]
    other_enabled = [row for row in rows if row.name not in {m.name for m in meta_rows} and _is_enabled(row)]
    return meta_rows, other_enabled

def _is_meta_source(row):
    text = " ".join(str(row.get(field) or "") for field in row.keys()).lower()
    return any(token in text for token in ("meta", "facebook", "fb", "instagram"))

def _is_enabled(row):
    if "enabled" in row and row.get("enabled") is not None:
        return bool(row.get("enabled"))
    if "disabled" in row and row.get("disabled") is not None:
        return not bool(row.get("disabled"))
    return True

def _disable_lead_sync_source(row):
    meta = frappe.get_meta("Lead Sync Source")
    values = {}
    if meta.has_field("enabled"):
        values["enabled"] = 0
    if meta.has_field("disabled"):
        values["disabled"] = 1
    if not values:
        return False
    frappe.db.set_value("Lead Sync Source", row.name, values, update_modified=False)
    return True

def _disable_scheduled_job():
    if not frappe.db.exists("DocType", "Scheduled Job Type"):
        return []
    meta = frappe.get_meta("Scheduled Job Type")
    method_field = "method" if meta.has_field("method") else None
    if not method_field:
        return []
    fields = ["name", method_field] + [field for field in ("stopped", "disabled") if meta.has_field(field)]
    rows = frappe.get_all("Scheduled Job Type", filters={method_field: CRM_SYNC_METHOD}, fields=fields)
    changed = []
    for row in rows:
        values = {}
        if meta.has_field("stopped"):
            values["stopped"] = 1
        if meta.has_field("disabled"):
            values["disabled"] = 1
        if values:
            frappe.db.set_value("Scheduled Job Type", row.name, values, update_modified=False)
            changed.append({"name": row.name, "values": values})
    return changed
