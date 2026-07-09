import json
import os
import frappe
from frappe.utils import add_to_date, get_datetime, now, now_datetime
from visa_crm.api.meta_utils import get_meta_settings, has_doctype, has_field, load_json, safe_json_dumps, set_if_has
from visa_crm.api.production_logging import log_event, timed_log

def _admin():
    if "System Manager" not in frappe.get_roles():
        frappe.throw("System Manager role required", frappe.PermissionError)

def _count(dt,filters=None):
    return frappe.db.count(dt,filters or {}) if has_doctype(dt) else 0

def _latest(dt,filters=None,fields=None):
    if not has_doctype(dt):
        return None
    rows=frappe.get_all(dt,filters=filters or {},fields=fields or ["name","creation","modified"],order_by="modified desc",limit=1)
    return rows[0] if rows else None

def _job_log(method):
    if not has_doctype("Scheduled Job Log"):
        return None
    for field in ("scheduled_job_type","method","job_type"):
        if has_field("Scheduled Job Log",field):
            rows=frappe.get_all("Scheduled Job Log",filters={field:["like",f"%{method}%"]},fields=["name","status","creation","modified"],order_by="creation desc",limit=1)
            return rows[0] if rows else None
    return None

@frappe.whitelist()
def production_health():
    _admin()
    with timed_log("production_health","dashboard"):
        queue_dt="Lead Intake Queue"
        latest_webhook=_latest(queue_dt,fields=_fields(queue_dt,("name","source_lead_id","status","creation","modified"))) if has_doctype(queue_dt) else None
        failed=_latest(queue_dt,{"status":"Failed"},_fields(queue_dt,("name","source_lead_id","last_error","modified"))) if has_doctype(queue_dt) else None
        graph_success=_latest(queue_dt,{"graph_payload":["is","set"]},["name","source_lead_id","modified"]) if has_doctype(queue_dt) and has_field(queue_dt,"graph_payload") else None
        scheduler=_job_log("visa_crm.api.intake_processor.process_pending")
        settings=get_meta_settings()
        health={"scheduler_running":bool(scheduler),"webhook_received_today":_webhook_today(),"queue_waiting":_count(queue_dt,{"status":"Lead Received"}),"queue_failed":_count(queue_dt,{"status":"Failed"}),"queue_processed":_count(queue_dt,{"status":"Processed"}),"meta_api_status":"configured" if settings and _token(settings) else "missing_token","gemini_status":"configured" if _gemini_configured() else "missing_key","last_webhook_time":latest_webhook.creation if latest_webhook else None,"last_scheduler_run":scheduler.creation if scheduler else None,"last_graph_api_success":graph_success.modified if graph_success else None,"last_graph_api_failure":failed.modified if failed else None,"latest_queue":latest_webhook,"latest_failure":failed}
        log_event("production_health","success","dashboard",**health)
        return health

@frappe.whitelist()
def queue_diagnostics(limit=100):
    _admin()
    fields=["name","status","source_lead_id","creation","modified"]
    optional=("retry_count","last_error","next_retry_at","processing_started_at","processing_completed_at","graph_payload","graph_api_request","graph_api_response","raw_payload")
    fields += [f for f in optional if has_field("Lead Intake Queue",f)]
    limit=min(max(int(limit or 100),1),200)
    rows=frappe.get_all("Lead Intake Queue",fields=fields,order_by="modified desc",limit=limit) if has_doctype("Lead Intake Queue") else []
    out=[]
    for row in rows:
        started=get_datetime(row.get("processing_started_at")) if row.get("processing_started_at") else None
        done=get_datetime(row.get("processing_completed_at")) if row.get("processing_completed_at") else None
        out.append({"name":row.name,"current_stage":row.status,"retry_count":row.get("retry_count") or 0,"last_api_response":_clip(row.get("graph_api_response") or row.get("graph_payload")),"graph_api_request":_clip(row.get("graph_api_request")) or row.get("source_lead_id"),"scheduler_timestamp":row.get("processing_started_at") or row.modified,"processing_duration":round((done-started).total_seconds(),2) if started and done else None,"failure_reason":row.get("last_error"),"modified":row.modified})
    log_event("queue_diagnostics","success","Lead Intake Queue",count=len(out))
    return out

@frappe.whitelist()
def meta_diagnostics(leadgen_id=None):
    _admin()
    settings=get_meta_settings()
    latest=_latest("Lead Intake Queue",fields=_fields("Lead Intake Queue",("name","source_lead_id","graph_payload","last_error","modified"))) if has_doctype("Lead Intake Queue") else None
    data={"page_access_token_valid":bool(settings and _token(settings)),"token_expiry":getattr(settings,"token_expiry",None) if settings else None,"page_id":getattr(settings,"page_id",None) if settings else None,"form_ids":getattr(settings,"form_ids",None) if settings else None,"permission_list":getattr(settings,"permissions",None) if settings else None,"latest_graph_api_call":latest.source_lead_id if latest else None,"latest_response":_clip(latest.get("graph_payload")) if latest else None,"latest_error":latest.get("last_error") if latest else None}
    if leadgen_id:
        data["manual_fetch"]=download_lead_by_id(leadgen_id)
    log_event("meta_diagnostics","success","Meta Settings",has_token=data["page_access_token_valid"])
    return data

@frappe.whitelist()
def scheduler_diagnostics():
    _admin()
    log=_job_log("visa_crm.api.intake_processor.process_pending")
    data={"last_execution":log.creation if log else None,"duration":None,"next_execution":None,"pending_jobs":_count("Lead Intake Queue",{"status":"Lead Received"}),"failed_jobs":_count("Lead Intake Queue",{"status":"Failed"}),"retry_jobs":_retry_jobs()}
    if log and has_field("Scheduled Job Log","duration"):
        data["duration"]=frappe.db.get_value("Scheduled Job Log",log.name,"duration")
    data["next_execution"]=add_to_date(now_datetime(),minutes=1)
    log_event("scheduler_diagnostics","success","scheduler",**data)
    return data

@frappe.whitelist()
def download_lead_by_id(leadgen_id):
    _admin()
    from visa_crm.api.meta_graph import fetch_lead
    with timed_log("meta_manual_fetch",leadgen_id):
        return fetch_lead(leadgen_id,get_meta_settings(),{"source_lead_id":leadgen_id,"status":"manual"})

@frappe.whitelist()
def replay_webhook(payload):
    _admin()
    data=load_json(payload,{}) if isinstance(payload,str) else payload
    leadgen_id=((data.get("value") or {}).get("leadgen_id") or data.get("leadgen_id") or data.get("source_lead_id"))
    if not leadgen_id:
        frappe.throw("leadgen_id is required")
    if frappe.db.exists("Lead Intake Queue",{"source_lead_id":leadgen_id}):
        return frappe.db.get_value("Lead Intake Queue",{"source_lead_id":leadgen_id},"name")
    doc=frappe.new_doc("Lead Intake Queue")
    for field,value in {"status":"Lead Received","lead_source":"Meta Instant Form","source_lead_id":leadgen_id,"raw_payload":safe_json_dumps(data)}.items():
        set_if_has(doc,field,value)
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    log_event("webhook_replay","success",doc.name,source_lead_id=leadgen_id)
    return doc.name

@frappe.whitelist()
def retry_queue(queue_name):
    _admin()
    from visa_crm.api.intake_processor import process_queue
    with timed_log("queue_retry",queue_name):
        process_queue(queue_name)
    return {"queued":queue_name}

@frappe.whitelist()
def rebuild_customer360(lead=None,customer=None,phone=None,email=None):
    _admin()
    from visa_crm.api.customer360 import match_lead_data
    data={"phone":phone,"email":email,"customer_name":customer or lead}
    result=match_lead_data(data,{"status":"admin_rebuild","source_lead_id":lead or customer})
    log_event("customer360_rebuild","success",lead or customer,result=result)
    return result

@frappe.whitelist()
def rebuild_communication_event(lead=None,customer=None,phone=None,email=None,content=None):
    _admin()
    if not has_doctype("Communication Event"):
        frappe.throw("Communication Event is not installed")
    event_id=f"admin:{lead or customer or phone or email or frappe.generate_hash(length=8)}"
    existing=frappe.db.exists("Communication Event",{"event_id":event_id})
    if existing:
        return existing
    doc=frappe.new_doc("Communication Event")
    for field,value in {"event_id":event_id,"event_type":"Note","source":"Manual","direction":"Inbound","lead":lead,"customer":customer,"phone":phone,"email":email,"content":content or "Admin rebuilt communication event","event_datetime":now()}.items():
        set_if_has(doc,field,value)
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    log_event("communication_event_rebuild","success",doc.name)
    return doc.name

@frappe.whitelist()
def reassign_counselor(lead,strategy="least_workload"):
    _admin()
    from visa_crm.api.lead_assignment import assign_lead
    employee=assign_lead(lead,None,strategy,{"status":"admin_reassign","source_lead_id":lead})
    log_event("counselor_reassign","success",lead,employee=employee)
    return employee

@frappe.whitelist()
def generate_demo(kind):
    _admin()
    kind=(kind or "").lower().replace(" ","_")
    return {"lead":_demo_lead,"customer":_demo_customer,"visa_application":_demo_visa,"communication_event":_demo_event,"payment":_demo_payment,"follow_up":_demo_followup}.get(kind,_bad_demo)()

@frappe.whitelist()
def deployment_verification():
    _admin()
    checks={}
    for dt in ("Workspace","Dashboard Chart","Number Card","Report","Print Format","Page","Role","Custom Field"):
        checks[dt]=_count(dt)>0 if has_doctype(dt) else False
    checks.update({"workspace":_exists("Workspace","Visa CRM"),"communication_center":_exists("Page","communication-center"),"ai_dashboard":_exists("Page","ai-insights-dashboard"),"portal_visa":os.path.exists(frappe.get_app_path("visa_crm","www","visa_portal.py")),"portal_upload":os.path.exists(frappe.get_app_path("visa_crm","www","document_upload.py")),"scheduler":bool(_job_log("visa_crm.api.intake_processor.process_pending"))})
    result={k:("PASS" if v else "FAIL") for k,v in checks.items()}
    log_event("deployment_verification","success","verification",result=result)
    return result

def _demo_lead():
    from visa_crm.api.manual_intake import create_manual_lead
    return create_manual_lead({"customer_name":"Demo Production Lead","phone":"+971500009999","email":"demo.production@example.com","visa_type":"Visit","country_interested":"UAE","source":"Manual"})

def _demo_customer():
    doc=frappe.new_doc("Customer")
    for field,value in {"customer_name":"Demo Production Customer","mobile_no":"+971500008888","email_id":"demo.customer@example.com"}.items():
        set_if_has(doc,field,value)
    doc.insert(ignore_permissions=True,ignore_if_duplicate=True)
    frappe.db.commit()
    return doc.name

def _demo_visa():
    if not has_doctype("Visa Application"):
        frappe.throw("Visa Application is missing")
    doc=frappe.new_doc("Visa Application")
    for field,value in {"applicant_name":"Demo Visa Applicant","visa_type":"Visit","country":"UAE","status":"Draft"}.items():
        set_if_has(doc,field,value)
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name

def _demo_event():
    return rebuild_communication_event(content="Demo production communication event")

def _demo_payment():
    if not has_doctype("Payment Schedule"):
        frappe.throw("Payment Schedule is missing")
    doc=frappe.new_doc("Payment Schedule")
    for field,value in {"amount":1000,"status":"Pending","due_date":frappe.utils.today()}.items():
        set_if_has(doc,field,value)
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name

def _demo_followup():
    doc=frappe.new_doc("ToDo")
    doc.description="Demo production follow-up"
    doc.status="Open"
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name

def _bad_demo():
    frappe.throw("Unsupported demo type")

def _retry_jobs():
    if not has_doctype("Lead Intake Queue") or not has_field("Lead Intake Queue","next_retry_at"):
        return 0
    return frappe.db.count("Lead Intake Queue",{"status":"Failed","next_retry_at":["is","set"]})

def _webhook_today():
    if not has_doctype("Lead Intake Queue"):
        return False
    return bool(frappe.get_all("Lead Intake Queue",filters={"creation":[">=",frappe.utils.today()]},limit=1))

def _gemini_configured():
    try:
        settings=frappe.get_single("Gemini Settings")
        return bool(settings.get_password("gemini_api_key"))
    except Exception:
        return False

def _token(settings):
    return settings.get_password("access_token") or getattr(settings,"access_token",None)

def _exists(dt,name):
    return bool(frappe.db.exists(dt,name)) if has_doctype(dt) else False

def _clip(value,length=1200):
    text=value if isinstance(value,str) else json.dumps(value,default=str)
    return text[:length] if text else None

def _fields(dt,names):
    return [f for f in names if f=="name" or has_field(dt,f)]
