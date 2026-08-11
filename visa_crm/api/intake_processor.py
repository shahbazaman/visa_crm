import frappe
from frappe.utils import add_to_date,get_datetime,now,now_datetime
from visa_crm.api.meta_utils import has_field,load_json,log_info,meta_debug_log,safe_json_dumps,set_values
from visa_crm.api.pipeline_engine import ensure_stage_ledger,next_eligible_stage,recover_expired_leases,rollup_queue,run_stage,stages_for
from visa_crm.api import pipeline_stage_services as services
from visa_crm.api.execution_history import ExecutionTimer

HANDLERS={"GRAPH_DOWNLOAD":services.graph_download,"NORMALIZE":services.normalize,"CLASSIFICATION":services.classification,"CUSTOMER360":services.customer360,"CRM_LEAD":services.crm_lead,"LEAD_WORKFLOW":services.lead_workflow,"VISA_APPLICATION":services.visa_application,"COMMUNICATION_EVENT":services.communication_event,"FOLLOW_UP":services.follow_up,"COUNSELOR_ASSIGNMENT":services.counselor_assignment,"AI_DISPATCH":services.ai_dispatch}
FAILURE_HANDLERS={"GRAPH_DOWNLOAD":services.graph_failure,"COUNSELOR_ASSIGNMENT":services.assignment_failure,"AI_DISPATCH":services.ai_dispatch_failure}

def process_pending(limit=100):
    timer=ExecutionTimer(stage="META_PIPELINE_SCHEDULER",execution_type="Scheduler",details={"limit":limit})
    meta_debug_log("process_pending_start",status="scheduler",limit=limit)
    rows=[]
    failures=0
    try:
        recover_expired_leases()
        services.recover_stale_ai_jobs()
        _recover_stale_fetches()
        rows=_pending_rows(limit)
        for row in rows:
            try:
                process_queue(row.name)
            except Exception as exc:
                failures+=1
                frappe.db.rollback()
                frappe.logger("visa_crm.pipeline").error(safe_json_dumps({"event":"queue_orchestration_failed","queue":row.name,"exception_class":f"{type(exc).__module__}.{type(exc).__qualname__}","error":str(exc),"traceback":frappe.get_traceback()}))
        timer.finish(result="WARNING" if failures else "SUCCESS",warning_count=failures,details={"queue_count":len(rows),"failure_count":failures})
        frappe.db.commit()
        meta_debug_log("process_pending_end",status="scheduler",count=len(rows),limit=limit)
        return len(rows)
    except Exception as exc:
        traceback=frappe.get_traceback()
        frappe.db.rollback()
        timer.finish(result="FAILED",failure_reason=str(exc),traceback=traceback,details={"queue_count":len(rows)})
        frappe.db.commit()
        raise

def process_queue(docname,stage_budget=20):
    if not frappe.db.exists("Lead Intake Queue",docname):
        return {"ok":False,"queue":docname,"error":"Lead Intake Queue not found"}
    ensure_stage_ledger(docname)
    frappe.db.commit()
    if _ignore_non_leadgen(docname):
        return _result(docname,[])
    executed=[]
    for _ in range(max(int(stage_budget or 20),1)):
        candidate=next_eligible_stage(docname,include_ai=True)
        if candidate and candidate.stage=="AI_GEMINI":
            services.dispatch_ai_job(docname)
            break
        if not candidate or candidate.stage not in HANDLERS:
            break
        outcome=run_stage(docname,HANDLERS[candidate.stage],stage=candidate.stage,include_ai=True,failure_handler=FAILURE_HANDLERS.get(candidate.stage))
        if not outcome:
            break
        executed.append({"stage":candidate.stage,"ok":bool(outcome.ok),"error":outcome.get("error")})
        if not outcome.ok and candidate.stage=="GRAPH_DOWNLOAD" and _ignored_test_event(docname):
            _ignore_queue(docname,"Ignored Meta testing event with an unsupported dummy lead ID")
            break
    _finalize(docname)
    result=_result(docname,executed)
    meta_debug_log("process_queue_end",queue_name=docname,source_lead_id=frappe.db.get_value("Lead Intake Queue",docname,"source_lead_id"),status=result.get("status"),orchestration_status=result.get("orchestration_status"),executed=executed)
    return result

def _pending_rows(limit):
    limit=max(int(limit or 100),1)
    names=[]
    initial=frappe.get_all("Lead Intake Queue",filters={"status":["in",["Lead Received","Fetching Meta Lead","Failed","Action Required","Needs Retry"]]},fields=["name"],order_by="creation asc",limit_page_length=limit)
    names.extend(row.name for row in initial)
    remaining=max(limit-len(names),0)
    if remaining and frappe.db.exists("DocType","Lead Intake Stage"):
        now_dt=now_datetime()
        rows=frappe.get_all("Lead Intake Stage",filters={"state":["in",["NOT_STARTED","FAILED","RUNNING"]]},fields=["queue","state","next_retry_at","lease_expires_at"],order_by="modified asc",limit_page_length=max(remaining*20,remaining))
        for row in rows:
            due=row.state=="NOT_STARTED" or row.state=="FAILED" and (not row.next_retry_at or get_datetime(row.next_retry_at)<=now_dt) or row.state=="RUNNING" and row.lease_expires_at and get_datetime(row.lease_expires_at)<=now_dt
            if due and row.queue not in names and next_eligible_stage(row.queue,include_ai=True,at=now_dt):
                names.append(row.queue)
                if len(names)>=limit:
                    break
    return [frappe._dict({"name":name}) for name in names]

def _recover_stale_fetches():
    if not has_field("Lead Intake Queue","processing_started_at"):
        return 0
    minutes=max(int(frappe.conf.get("visa_crm_meta_stale_minutes") or 10),1)
    cutoff=add_to_date(now_datetime(),minutes=-minutes)
    current=now_datetime()
    frappe.db.sql("""update `tabLead Intake Queue` set status=%s,last_error=%s,next_retry_at=%s,processing_completed_at=%s where status=%s and ((processing_started_at is not null and processing_started_at<=%s) or (processing_started_at is null and modified<=%s))""",("Needs Retry","Recovered legacy stale Fetching Meta Lead queue item",current,current,"Fetching Meta Lead",cutoff,cutoff))
    recovered=frappe.db._cursor.rowcount
    if recovered:
        frappe.db.commit()
        log_info("meta_stale_queue_recovered",count=recovered,cutoff=cutoff)
    return recovered

def _update_queue(doc,data,graph_payload,status):
    values={field:data.get(field) for field in ("source_lead_id","customer_name","phone","email","country_interested","visa_type","campaign_name","campaign_id","adset_name","adset_id","ad_name","ad_id")}
    values.update({"status":status,"graph_payload":safe_json_dumps(graph_payload),"graph_api_response":safe_json_dumps(graph_payload),"custom_answers":safe_json_dumps(data.get("custom_answers")),"page_id":data.get("page_id") or doc.get("page_id"),"form_id":data.get("form_id") or doc.get("form_id")})
    set_values("Lead Intake Queue",doc.name,values)
    _sync_webhook_event(doc.name,{"graph_api_response":safe_json_dumps(graph_payload),"queue_status":status})
    doc.reload()

def _ignore_non_leadgen(queue_name):
    event_type=frappe.db.get_value("Lead Intake Queue",queue_name,"event_type") if has_field("Lead Intake Queue","event_type") else None
    if not event_type:
        payload=load_json(frappe.db.get_value("Lead Intake Queue",queue_name,"raw_payload"),{})
        event_type=(payload.get("change") or {}).get("field")
    if event_type and event_type!="leadgen":
        _ignore_queue(queue_name,f"Ignored Meta event field {event_type}; only leadgen events are processed")
        return True
    return False

def _ignore_queue(queue_name,reason):
    now_dt=now_datetime()
    frappe.db.sql("""update `tabLead Intake Stage` set state='SKIPPED',skip_reason=%s,completed_at=%s,next_retry_at=null,lease_owner=null,lease_token=null,lease_expires_at=null where queue=%s and stage!='WEBHOOK' and state!='COMPLETED'""",(reason,now_dt,queue_name))
    set_values("Lead Intake Queue",queue_name,{"status":"Ignored Test Event","orchestration_status":"IGNORED","current_stage":None,"next_action_at":None,"processing_completed_at":now_dt,"last_error":reason})
    _sync_webhook_event(queue_name,{"queue_status":"Ignored Test Event"})
    frappe.db.commit()

def _ignored_test_event(queue_name):
    leadgen_id=str(frappe.db.get_value("Lead Intake Queue",queue_name,"source_lead_id") or "").strip()
    subcode=str(frappe.db.get_value("Lead Intake Queue",queue_name,"graph_error_subcode") or "") if has_field("Lead Intake Queue","graph_error_subcode") else ""
    message=str(frappe.db.get_value("Lead Intake Queue",queue_name,"graph_error_message") or "").lower() if has_field("Lead Intake Queue","graph_error_message") else ""
    dummy=leadgen_id in ("444444444444","987654321") or leadgen_id.startswith("manual-") or (leadgen_id.isdigit() and len(leadgen_id)<=12) or (not leadgen_id.isdigit() and not leadgen_id.startswith("127"))
    return dummy and (subcode=="33" or "unsupported get request" in message or leadgen_id.startswith("manual-"))

def _finalize(queue_name):
    rollup=rollup_queue(queue_name)
    values={}
    if rollup and rollup.status in ("COMPLETED","COMPLETED_WITH_WARNINGS"):
        values["processing_completed_at"]=now()
        values["next_retry_at"]=None
        if rollup.status=="COMPLETED":
            values["last_error"]=""
    if values:
        set_values("Lead Intake Queue",queue_name,values)
    queue=frappe.get_doc("Lead Intake Queue",queue_name)
    if rollup and rollup.status in ("COMPLETED","COMPLETED_WITH_WARNINGS"):
        _sync_webhook_event(queue_name,{"queue_status":queue.status,"crm_lead":queue.get("matched_lead"),"customer":queue.get("matched_customer"),"visa_application":queue.get("visa_application"),"communication_event":queue.get("communication_event")})
    frappe.db.commit()

def _result(queue_name,executed):
    queue=frappe.get_doc("Lead Intake Queue",queue_name)
    return {"ok":queue.orchestration_status in ("COMPLETED","COMPLETED_WITH_WARNINGS"),"queue":queue.name,"status":queue.status,"orchestration_status":queue.orchestration_status,"current_stage":queue.current_stage,"lead":queue.get("matched_lead"),"customer":queue.get("matched_customer"),"visa_application":queue.get("visa_application"),"communication_event":queue.get("communication_event"),"followup":queue.get("followup_reference"),"assigned_employee":queue.get("assigned_employee"),"ai_status":queue.get("ai_status"),"executed":executed,"stages":stages_for(queue_name)}

def _sync_webhook_event(queue_name,values):
    if not has_field("Lead Intake Queue","meta_webhook_event"):
        return
    event=frappe.db.get_value("Lead Intake Queue",queue_name,"meta_webhook_event")
    if event:
        set_values("Meta Webhook Event",event,{field:value for field,value in values.items() if value is not None})
