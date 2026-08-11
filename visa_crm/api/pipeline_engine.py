import os
import socket
import uuid
import frappe
from frappe.utils import add_to_date,cint,get_datetime,now_datetime,time_diff_in_seconds
from visa_crm.api.execution_history import record
from visa_crm.api.meta_utils import load_json,safe_json_dumps
from visa_crm.api.stage_definitions import AI_STAGES,BUSINESS_STAGES,PIPELINE_VERSION,STAGES,STAGE_BY_NAME

DEFAULT_LEASE_SECONDS=300
TERMINAL_STATES=("COMPLETED","SKIPPED")

class StageClaimError(RuntimeError):
    pass

def ensure_stage_ledger(queue_name):
    existing=set(frappe.get_all("Lead Intake Stage",filters={"queue":queue_name},pluck="stage"))
    for definition in STAGES:
        if definition["stage"] in existing:
            continue
        doc=frappe.new_doc("Lead Intake Stage")
        doc.update({"stage_key":stage_key(queue_name,definition["stage"]),"queue":queue_name,"stage":definition["stage"],"sequence":definition["sequence"],"parent_stage":definition.get("parent_stage"),"requirement_class":definition["requirement_class"],"state":"NOT_STARTED","attempt_count":0,"max_attempts":definition["max_attempts"]})
        doc.insert(ignore_permissions=True,ignore_if_duplicate=True)
    _ensure_webhook_complete(queue_name)
    repair_normalization_checkpoint(queue_name)
    rollup_queue(queue_name)

def repair_normalization_checkpoint(queue_name):
    norm=load_json(frappe.db.get_value("Lead Intake Queue",queue_name,"normalized_payload"),{})
    has_pii=bool(norm and (norm.get("customer_name") or norm.get("phone") or norm.get("email")))
    row=_stage_row(queue_name,"NORMALIZE")
    if not row or row.state!="COMPLETED":
        return False
    if norm and has_pii:
        return False
    queue=frappe.db.get_value("Lead Intake Queue",queue_name,["graph_payload","graph_api_response","custom_answers","customer_name","phone","email"],as_dict=True) or {}
    graph=load_json(queue.get("graph_payload"),{}) or load_json(queue.get("graph_api_response"),{})
    if not graph:
        stage_res=frappe.db.get_value("Lead Intake Stage",f"{queue_name}:GRAPH_DOWNLOAD","result_json")
        if stage_res:
            res_data=load_json(stage_res,{})
            graph=res_data.get("graph_payload") or res_data.get("result")
    valid_graph=bool(graph and isinstance(graph,dict) and not graph.get("error") and (graph.get("id") or graph.get("field_data")))
    if not (queue.get("custom_answers") or queue.get("customer_name") or queue.get("phone") or queue.get("email") or valid_graph):
        return False
    now=now_datetime()
    frappe.db.set_value("Lead Intake Stage",row.name,{"state":"NOT_STARTED","completed_at":None,"duration_ms":0,"next_retry_at":None,"lease_owner":None,"lease_token":None,"lease_expires_at":None,"heartbeat_at":None,"result_doctype":None,"result_name":None,"result_json":None,"last_error_class":None,"last_error":None,"last_traceback":None,"warning":0,"skip_reason":None},update_modified=False)
    customer=_stage_row(queue_name,"CUSTOMER360")
    if customer and customer.state=="FAILED" and "Normalized payload is missing" in str(frappe.db.get_value("Lead Intake Stage",customer.name,"last_error") or ""):
        frappe.db.set_value("Lead Intake Stage",customer.name,{"next_retry_at":now,"max_attempts":max(cint(customer.max_attempts),cint(customer.attempt_count)+1)},update_modified=False)
    _logger().info(safe_json_dumps({"event":"normalization_checkpoint_repaired","queue":queue_name,"reason":"completed_normalize_stage_without_durable_normalized_payload"}))
    return True

def stage_key(queue_name,stage):
    return f"{queue_name}:{stage}"

def stages_for(queue_name):
    return frappe.get_all("Lead Intake Stage",filters={"queue":queue_name},fields=["name","queue","stage","sequence","requirement_class","state","attempt_count","max_attempts","next_retry_at","lease_owner","lease_token","lease_expires_at","heartbeat_at","started_at","completed_at","duration_ms","last_error_class","last_error","last_traceback","result_doctype","result_name","result_json","warning","skip_reason"],order_by="sequence asc")

def next_eligible_stage(queue_name,include_ai=False,at=None):
    at=get_datetime(at or now_datetime())
    rows=stages_for(queue_name)
    states={row.stage:row.state for row in rows}
    allowed=set(STAGE_BY_NAME) if include_ai else set(BUSINESS_STAGES)
    for row in rows:
        if row.stage not in allowed or not _dependencies_complete(row.stage,states):
            continue
        if row.state in ("NOT_STARTED", "BLOCKED"):
            return row
        if row.state=="FAILED" and _retry_due(row,at) and _attempts_available(row):
            return row
        if row.state=="RUNNING" and row.lease_expires_at and get_datetime(row.lease_expires_at)<=at:
            return row
    return None

def claim_stage(queue_name,stage=None,include_ai=False,lease_seconds=None,owner=None):
    ensure_stage_ledger(queue_name)
    at=now_datetime()
    candidate=_stage_row(queue_name,stage) if stage else next_eligible_stage(queue_name,include_ai=include_ai,at=at)
    if not candidate or candidate.state in TERMINAL_STATES or not _dependencies_complete(candidate.stage,_states(queue_name)):
        return None
    if candidate.state=="FAILED" and (not _retry_due(candidate,at) or not _attempts_available(candidate)):
        return None
    if candidate.state=="RUNNING" and (not candidate.lease_expires_at or get_datetime(candidate.lease_expires_at)>at):
        return None
    token=uuid.uuid4().hex
    owner=owner or _worker_owner()
    expires=add_to_date(at,seconds=max(cint(lease_seconds or frappe.conf.get("visa_crm_stage_lease_seconds") or DEFAULT_LEASE_SECONDS),30))
    frappe.db.sql("""update `tabLead Intake Stage` set state='RUNNING',attempt_count=attempt_count+1,lease_owner=%s,lease_token=%s,lease_expires_at=%s,heartbeat_at=%s,started_at=%s,completed_at=null,duration_ms=0,last_error_class=null,last_error=null,last_traceback=null,warning=0,skip_reason=null,modified=%s where name=%s and ((state='NOT_STARTED') or (state='FAILED' and (next_retry_at is null or next_retry_at<=%s)) or (state='RUNNING' and lease_expires_at is not null and lease_expires_at<=%s))""",(owner,token,expires,at,at,at,candidate.name,at,at))
    if frappe.db._cursor.rowcount!=1:
        frappe.db.rollback()
        return None
    if candidate.stage not in AI_STAGES:
        _update_queue_running(queue_name,candidate.stage,at)
    record(queue=queue_name,stage=candidate.stage,execution_type="Automatic Retry" if cint(candidate.attempt_count) else "Stage",result="RUNNING",retry_count=cint(candidate.attempt_count),next_retry=None,details={"lease_token":token,"lease_expires_at":expires})
    frappe.db.commit()
    return frappe._dict({"name":candidate.name,"queue":queue_name,"stage":candidate.stage,"lease_token":token,"lease_owner":owner,"lease_expires_at":expires,"attempt_count":cint(candidate.attempt_count)+1})

def renew_stage_lease(claim,lease_seconds=None,commit=True):
    _validate_claim(claim)
    at=now_datetime()
    expires=add_to_date(at,seconds=max(cint(lease_seconds or frappe.conf.get("visa_crm_stage_lease_seconds") or DEFAULT_LEASE_SECONDS),30))
    frappe.db.sql("""update `tabLead Intake Stage` set heartbeat_at=%s,lease_expires_at=%s,modified=%s where name=%s and state='RUNNING' and lease_token=%s""",(at,expires,at,claim.name,claim.lease_token))
    if frappe.db._cursor.rowcount!=1:
        frappe.db.rollback()
        raise StageClaimError(f"Stage lease is no longer valid: {claim.name}")
    if commit:
        frappe.db.commit()
    claim.lease_expires_at=expires
    return expires

def complete_stage(claim,result=None,result_doctype=None,result_name=None,input_hash=None,output_hash=None,warning=False):
    _validate_claim(claim)
    now=now_datetime()
    started=frappe.db.get_value("Lead Intake Stage",claim.name,"started_at")
    duration=max(int(time_diff_in_seconds(now,started or now)*1000),0)
    frappe.db.sql("""update `tabLead Intake Stage` set state='COMPLETED',completed_at=%s,duration_ms=%s,next_retry_at=null,lease_owner=null,lease_token=null,lease_expires_at=null,input_hash=%s,output_hash=%s,result_doctype=%s,result_name=%s,result_json=%s,warning=%s,last_error_class=null,last_error=null,last_traceback=null,modified=%s where name=%s and state='RUNNING' and lease_token=%s""",(now,duration,input_hash,output_hash,result_doctype,result_name,safe_json_dumps(result) if result is not None else None,cint(warning),now,claim.name,claim.lease_token))
    if frappe.db._cursor.rowcount!=1:
        raise StageClaimError(f"Stage lease is no longer valid: {claim.name}")
    rollup_queue(claim.queue,progress=True)

def fail_stage(claim,exc,traceback=None,retry_at=None,warning=None):
    _validate_claim(claim)
    now=now_datetime()
    started=frappe.db.get_value("Lead Intake Stage",claim.name,"started_at")
    duration=max(int(time_diff_in_seconds(now,started or now)*1000),0)
    definition=STAGE_BY_NAME[claim.stage]
    warning=definition["requirement_class"]=="Optional" if warning is None else warning
    retry_at=retry_at or _default_retry_at(claim.stage,cint(claim.attempt_count),now)
    frappe.db.sql("""update `tabLead Intake Stage` set state='FAILED',duration_ms=%s,next_retry_at=%s,lease_owner=null,lease_token=null,lease_expires_at=null,last_error_class=%s,last_error=%s,last_traceback=%s,warning=%s,modified=%s where name=%s and state='RUNNING' and lease_token=%s""",(duration,retry_at,_exception_class(exc),str(exc)[:4000],traceback,cint(warning),now,claim.name,claim.lease_token))
    if frappe.db._cursor.rowcount!=1:
        raise StageClaimError(f"Stage lease is no longer valid: {claim.name}")
    if frappe.db.exists("DocType","Lead Intake Queue"):
        queue_values={"last_error":str(exc)[:4000]}
        if frappe.get_meta("Lead Intake Queue").has_field("last_error_class"):
            queue_values["last_error_class"]=_exception_class(exc)
        if frappe.get_meta("Lead Intake Queue").has_field("last_traceback") and traceback:
            queue_values["last_traceback"]=traceback[:8000]
        frappe.db.set_value("Lead Intake Queue",claim.queue,queue_values,update_modified=False)
    rollup_queue(claim.queue,progress=True)

def skip_stage(queue_name,stage,reason):
    if not reason:
        raise ValueError("A skip reason is required")
    definition=STAGE_BY_NAME[stage]
    if definition["requirement_class"]!="Optional":
        raise ValueError(f"Required stage cannot be skipped: {stage}")
    frappe.db.set_value("Lead Intake Stage",stage_key(queue_name,stage),{"state":"SKIPPED","skip_reason":reason,"completed_at":now_datetime(),"next_retry_at":None,"lease_owner":None,"lease_token":None,"lease_expires_at":None},update_modified=False)
    rollup_queue(queue_name,progress=True)

def run_stage(queue_name,handler,stage=None,include_ai=False,lease_seconds=None,failure_handler=None):
    claim=claim_stage(queue_name,stage=stage,include_ai=include_ai,lease_seconds=lease_seconds)
    if not claim:
        return None
    try:
        renew_stage_lease(claim,lease_seconds=lease_seconds)
        result=handler(queue_name,claim)
        renew_stage_lease(claim,lease_seconds=lease_seconds,commit=False)
        payload=result if isinstance(result,dict) else {"result":result}
        complete_stage(claim,result=payload,result_doctype=payload.get("result_doctype"),result_name=payload.get("result_name"),input_hash=payload.get("input_hash"),output_hash=payload.get("output_hash"),warning=payload.get("warning",False))
        row=frappe.db.get_value("Lead Intake Stage",claim.name,["duration_ms","warning"],as_dict=True) or {}
        record(queue=queue_name,stage=claim.stage,execution_type="Completion",result="WARNING" if row.get("warning") else "SUCCESS",duration_ms=row.get("duration_ms"),retry_count=max(cint(claim.attempt_count)-1,0),warning_count=cint(row.get("warning")),details=payload)
        frappe.db.commit()
        return frappe._dict({"ok":True,"claim":claim,"result":payload})
    except Exception as exc:
        traceback=frappe.get_traceback()
        frappe.db.rollback()
        if failure_handler:
            try:
                failure_handler(queue_name,claim,exc,traceback)
            except Exception:
                frappe.db.rollback()
                _logger().error(safe_json_dumps({"event":"stage_failure_handler_failed","queue":queue_name,"stage":claim.stage,"original_error":str(exc),"traceback":frappe.get_traceback()}))
        fail_stage(claim,exc,traceback=traceback)
        row=frappe.db.get_value("Lead Intake Stage",claim.name,["duration_ms","next_retry_at","warning"],as_dict=True) or {}
        record(queue=queue_name,stage=claim.stage,execution_type="Retry",result="FAILED",duration_ms=row.get("duration_ms"),retry_count=cint(claim.attempt_count),warning_count=cint(row.get("warning")),failure_reason=str(exc),next_retry=row.get("next_retry_at"),traceback=traceback)
        frappe.db.commit()
        _logger().error(safe_json_dumps({"event":"stage_failed","queue":queue_name,"stage":claim.stage,"attempt":claim.attempt_count,"exception_class":_exception_class(exc),"error":str(exc),"traceback":traceback}))
        return frappe._dict({"ok":False,"claim":claim,"error":str(exc),"exception_class":_exception_class(exc)})

def recover_expired_leases(at=None):
    at=get_datetime(at or now_datetime())
    rows=frappe.get_all("Lead Intake Stage",filters={"state":"RUNNING","lease_expires_at":["<=",at]},fields=["name","queue","stage","attempt_count","lease_token"])
    queues=set()
    for row in rows:
        frappe.db.sql("""update `tabLead Intake Stage` set state='FAILED',next_retry_at=%s,lease_owner=null,lease_token=null,lease_expires_at=null,last_error_class='WorkerLeaseExpired',last_error='Worker lease expired before stage completion',warning=%s,modified=%s where name=%s and state='RUNNING' and lease_token=%s""",(at,cint(STAGE_BY_NAME[row.stage]["requirement_class"]=="Optional"),at,row.name,row.lease_token))
        if frappe.db._cursor.rowcount:
            queues.add(row.queue)
            record(queue=row.queue,stage=row.stage,execution_type="Stale Recovery",result="RECOVERED",retry_count=cint(row.attempt_count),failure_reason="Worker lease expired before stage completion",next_retry=at,details={"expired_lease_token":row.lease_token})
    for queue_name in queues:
        rollup_queue(queue_name,progress=True)
    if rows:
        frappe.db.commit()
    return len(queues),len(rows)

def retry_stage(queue_name,stage,force=False):
    row=_stage_row(queue_name,stage)
    if not row or (not force and row.state not in ("FAILED","RUNNING")):
        return False
    if row.state=="RUNNING" and not force and (not row.lease_expires_at or get_datetime(row.lease_expires_at)>now_datetime()):
        return False
    values={"state":"FAILED","next_retry_at":now_datetime(),"lease_owner":None,"lease_token":None,"lease_expires_at":None}
    if cint(row.max_attempts) and cint(row.attempt_count)>=cint(row.max_attempts):
        values["max_attempts"]=cint(row.attempt_count)+1
    frappe.db.set_value("Lead Intake Stage",row.name,values,update_modified=False)
    rollup_queue(queue_name,progress=True)
    record(queue=queue_name,stage=stage,execution_type="Retry",result="RECOVERED",retry_count=cint(row.attempt_count),next_retry=values["next_retry_at"],details={"forced":bool(force)})
    frappe.db.commit()
    return True

def rollup_queue(queue_name,progress=False):
    rows=stages_for(queue_name)
    if not rows:
        return None
    states={row.stage:row.state for row in rows}
    for row in rows:
        if row.state in ("NOT_STARTED", "BLOCKED"):
            failed_deps = [dep for dep in STAGE_BY_NAME[row.stage].get("dependencies", ()) if states.get(dep) == "FAILED" and not (row.stage == "NORMALIZE" and dep == "GRAPH_DOWNLOAD")]
            if failed_deps:
                if row.state != "BLOCKED":
                    frappe.db.set_value("Lead Intake Stage", row.name, {"state": "BLOCKED", "skip_reason": f"Blocked by failed dependency: {', '.join(failed_deps)}"}, update_modified=False)
                    row.state = "BLOCKED"
                    states[row.stage] = "BLOCKED"
            elif row.state == "BLOCKED":
                frappe.db.set_value("Lead Intake Stage", row.name, {"state": "NOT_STARTED", "skip_reason": None}, update_modified=False)
                row.state = "NOT_STARTED"
                states[row.stage] = "NOT_STARTED"
    business=[row for row in rows if row.stage in BUSINESS_STAGES]
    required=[row for row in business if row.requirement_class!="Optional"]
    optional=[row for row in business if row.requirement_class=="Optional"]
    failed_required=[row for row in required if row.state=="FAILED"]
    failed_optional=[row for row in optional if row.state=="FAILED"]
    lead_complete=states.get("CRM_LEAD")=="COMPLETED"
    if frappe.db.get_value("Lead Intake Queue",queue_name,"status")=="Ignored Test Event":
        overall="IGNORED"
    elif any(row.state=="RUNNING" for row in business):
        overall="RUNNING"
    elif failed_required:
        overall="PARTIALLY_COMPLETED" if lead_complete else "FAILED"
    elif lead_complete and not all(row.state in TERMINAL_STATES for row in required):
        overall="PARTIALLY_COMPLETED"
    elif lead_complete and failed_optional:
        overall="COMPLETED_WITH_WARNINGS"
    elif lead_complete and all(row.state in TERMINAL_STATES for row in required) and all(row.state in TERMINAL_STATES for row in optional):
        overall="COMPLETED"
    elif lead_complete:
        overall="PARTIALLY_COMPLETED"
    else:
        overall="PENDING"
    current=_current_stage(rows)
    created_at = get_datetime(frappe.db.get_value("Lead Intake Queue", queue_name, "creation") or now_datetime())
    valid_retries = [get_datetime(row.next_retry_at) for row in rows if row.state == "FAILED" and row.next_retry_at and get_datetime(row.next_retry_at) >= add_to_date(created_at, minutes=-5)]
    next_action = min(valid_retries, default=None)
    warnings=sum(1 for row in rows if row.warning or row.state=="FAILED" and STAGE_BY_NAME[row.stage]["requirement_class"]=="Optional")
    summary={row.stage:{"state":row.state,"attempts":cint(row.attempt_count),"duration_ms":cint(row.duration_ms),"next_retry_at":str(row.next_retry_at) if row.next_retry_at else None,"error":row.last_error} for row in rows}
    values={"orchestration_status":overall,"pipeline_version":PIPELINE_VERSION,"current_stage":current,"next_action_at":next_action,"warning_count":warnings,"stage_summary_json":safe_json_dumps(summary)}
    if progress:
        values["last_progress_at"]=now_datetime()
    legacy=_legacy_status(overall,states,failed_required)
    if legacy:
        values["status"]=legacy
    frappe.db.set_value("Lead Intake Queue",queue_name,values,update_modified=False)
    return frappe._dict({"status":overall,"current_stage":current,"warning_count":warnings,"next_action_at":next_action})

def _ensure_webhook_complete(queue_name):
    name=stage_key(queue_name,"WEBHOOK")
    if frappe.db.get_value("Lead Intake Stage",name,"state")=="NOT_STARTED":
        frappe.db.set_value("Lead Intake Stage",name,{"state":"COMPLETED","completed_at":frappe.db.get_value("Lead Intake Queue",queue_name,"creation"),"result_doctype":"Lead Intake Queue","result_name":queue_name},update_modified=False)

def _stage_row(queue_name,stage):
    if stage not in STAGE_BY_NAME:
        raise ValueError(f"Unknown pipeline stage: {stage}")
    rows=frappe.get_all("Lead Intake Stage",filters={"queue":queue_name,"stage":stage},fields=["name","queue","stage","state","attempt_count","max_attempts","next_retry_at","lease_token","lease_expires_at"],limit=1)
    return rows[0] if rows else None

def _states(queue_name):
    return dict(frappe.get_all("Lead Intake Stage",filters={"queue":queue_name},fields=["stage","state"],as_list=True))

def _dependencies_complete(stage,states):
    for dependency in STAGE_BY_NAME[stage].get("dependencies",()):
        dep_state = states.get(dependency)
        if dep_state in TERMINAL_STATES:
            continue
        if stage == "NORMALIZE" and dependency == "GRAPH_DOWNLOAD" and dep_state == "FAILED":
            continue
        return False
    return True

def _retry_due(row,at):
    return not row.next_retry_at or get_datetime(row.next_retry_at)<=at

def _attempts_available(row):
    return not cint(row.max_attempts) or cint(row.attempt_count)<cint(row.max_attempts)

def _validate_claim(claim):
    if not claim or not getattr(claim,"name",None) or not getattr(claim,"lease_token",None):
        raise StageClaimError("A valid stage claim is required")

def _default_retry_at(stage,attempt,at):
    if stage=="COUNSELOR_ASSIGNMENT":
        return add_to_date(at,minutes=15)
    if stage in AI_STAGES:
        delays=(30,120,300,600,1800)
        return add_to_date(at,seconds=delays[attempt-1] if 1<=attempt<=len(delays) else 3600)
    return add_to_date(at,minutes=min(60,2**min(max(attempt,1),6)))

def _current_stage(rows):
    running=next((row.stage for row in rows if row.state=="RUNNING"),None)
    if running:
        return running
    return next((row.stage for row in rows if row.state=="FAILED" and _attempts_available(row)),next((row.stage for row in rows if row.state=="FAILED"),next((row.stage for row in rows if row.state=="NOT_STARTED"),None)))

def _legacy_status(overall,states,failed):
    if overall=="IGNORED":
        return "Ignored Test Event"
    if overall=="COMPLETED":
        return "Processed"
    if overall=="COMPLETED_WITH_WARNINGS" and states.get("CRM_LEAD")=="COMPLETED":
        return "Processed With Warnings"
    if overall in ("FAILED","PARTIALLY_COMPLETED"):
        exhausted=any(not _attempts_available(row) for row in failed)
        return "Action Required" if exhausted else "Needs Retry"
    return None

def _update_queue_running(queue_name,stage,at):
    frappe.db.set_value("Lead Intake Queue",queue_name,{"orchestration_status":"RUNNING","current_stage":stage,"last_progress_at":at},update_modified=False)

def _worker_owner():
    return f"{frappe.local.site or 'site'}:{socket.gethostname()}:{os.getpid()}"

def _exception_class(exc):
    return f"{type(exc).__module__}.{type(exc).__qualname__}"

def _logger():
    logger=frappe.logger("visa_crm.pipeline")
    logger.setLevel("INFO")
    return logger
