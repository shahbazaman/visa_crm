import importlib
import os
import frappe

PAGES={"production-health":"Production Health","lead-queue-diagnostics":"Lead Queue Diagnostics","meta-diagnostics":"Meta Diagnostics","scheduler-diagnostics":"Scheduler Diagnostics","production-tools":"Production Tools"}
REQUIRED={"Workspace":["Visa CRM"],"Page":["communication-center","ai-insights-dashboard"]+list(PAGES),"Report":["Lead Conversion","Revenue","Employee Performance","Source Performance","Visa Processing","Pending Documents","Lost Lead Analysis"],"Print Format":["Visa Application","Customer Profile","Payment Receipt","Document Checklist"],"Number Card":["New Leads","Active Leads","Pending Documents","Visa Processing","Approved Visas","Overdue Follow-ups"],"Dashboard Chart":["Visa Lead Stage Mix","Visa Source Performance","Visa Application Pipeline","Document Verification Status","Payment Collection Status"],"Kanban Board":["CRM Lead by Stage"]}
ENDPOINTS=("visa_crm.api.production_diagnostics.production_health","visa_crm.api.production_diagnostics.queue_diagnostics","visa_crm.api.production_diagnostics.meta_diagnostics","visa_crm.api.production_diagnostics.scheduler_diagnostics","visa_crm.api.production_diagnostics.deployment_verification","visa_crm.api.production_diagnostics.generate_demo","visa_crm.api.production_diagnostics.retry_queue","visa_crm.api.production_diagnostics.download_lead_by_id")

def execute():
    _pages()
    result=_verify()
    frappe.logger("visa_crm.production").info("Visa CRM production integration verification "+frappe.as_json(result))
    frappe.clear_cache()

def _pages():
    for name,title in PAGES.items():
        if frappe.db.exists("Page",name):
            continue
        try:
            frappe.get_doc({"doctype":"Page","page_name":name,"title":title,"module":"Visa CRM","standard":"Yes"}).insert(ignore_permissions=True,ignore_if_duplicate=True)
        except Exception:
            frappe.logger("visa_crm.production").warning(f"Page create skipped {name}: {frappe.get_traceback()}")

def _verify():
    out={}
    for dt,names in REQUIRED.items():
        out[dt]={name:("PASS" if frappe.db.exists(dt,name) else "FAIL") for name in names} if frappe.db.exists("DocType",dt) else {"doctype":"FAIL"}
    out["Portal"]={"visa-portal":"PASS" if os.path.exists(frappe.get_app_path("visa_crm","www","visa_portal.py")) else "FAIL","document-upload":"PASS" if os.path.exists(frappe.get_app_path("visa_crm","www","document_upload.py")) else "FAIL"}
    out["Custom Fields"]={dt:_field_status(dt) for dt in ("CRM Lead","Customer","Communication Event","Visa Application","Lead Intake Queue")}
    out["APIs"]={path:_endpoint(path) for path in ENDPOINTS}
    out["Scheduler"]="PASS" if _scheduler_hook() else "FAIL"
    return out

def _field_status(dt):
    if not frappe.db.exists("DocType",dt):
        return "FAIL"
    meta=frappe.get_meta(dt)
    fields={"CRM Lead":["country","visa_type","customer360","assigned_counselor","timeline","communication_history","visa_applications","documents","payments"],"Customer":["customer360","assigned_counselor","timeline","communication_history","visa_applications","documents","payments"],"Communication Event":["ai_next_best_action","ai_customer_priority","conversation_status"],"Visa Application":["lead","customer","country","visa_type"],"Lead Intake Queue":["retry_count","last_error","next_retry_at","communication_event"]}.get(dt,[])
    return {field:("PASS" if meta.has_field(field) else "FAIL") for field in fields}

def _endpoint(path):
    try:
        module,name=path.rsplit(".",1)
        return "PASS" if callable(getattr(importlib.import_module(module),name,None)) else "FAIL"
    except Exception:
        return "FAIL"

def _scheduler_hook():
    try:
        import visa_crm.hooks as hooks
        cron=(getattr(hooks,"scheduler_events",{}).get("cron") or {})
        return any("visa_crm.api.intake_processor.process_pending" in jobs for jobs in cron.values())
    except Exception:
        return False
