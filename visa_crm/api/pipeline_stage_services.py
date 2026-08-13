import hashlib
import json
import os
import socket
import uuid
import frappe
from frappe.utils import add_to_date,cint,get_datetime,now,now_datetime
from visa_crm.api.meta_graph import GRAPH_VERSION,LEAD_FIELDS,fetch_lead,is_synthetic_leadgen_id,PermanentGraphError
from visa_crm.api.meta_mapping import MAPPING_VERSION,normalize_lead
from visa_crm.api.meta_utils import get_meta_settings,has_field,load_json,log_info,safe_json_dumps,set_values
from visa_crm.api.customer360 import resolve_customer,resolve_lead
from visa_crm.api.followup import create_meta_followup
from visa_crm.api.lead_assignment import assign_lead, NotApplicable
from visa_crm.api.visa_application import create_for_lead
from visa_crm.api.workflow import create_deal_if_supported,mark_lead_stage,qualify_lead
from visa_crm.api.execution_history import record
from visa_crm.api.lead_classification import classify_queue,sync_lead_classification

class NoEligibleCounselor(RuntimeError):
    """Raised when a supported department has no eligible counselors (retryable)."""
    pass

def graph_download(queue_name,claim=None):
    queue=frappe.get_doc("Lead Intake Queue",queue_name)
    source_lead_id=queue.source_lead_id
    if not source_lead_id or str(source_lead_id).strip().lower() in ("none", "null", "0", ""):
        source_lead_id=_recover_source_lead_id(queue)
        if source_lead_id:
            set_values("Lead Intake Queue",queue_name,{"source_lead_id":source_lead_id})
            queue.reload()
    if not source_lead_id or str(source_lead_id).strip().lower() in ("none", "null", "0", ""):
        raise ValueError(f"GRAPH_DOWNLOAD cannot execute: Meta leadgen ID is missing for queue {queue_name}")
    existing=_successful_graph_payload(queue)
    request=_graph_request(source_lead_id)
    if existing:
        digest=_hash(existing)
        _set_if_blank(queue_name,{"graph_payload_hash":digest,"graph_api_request":safe_json_dumps(request)})
        return {"graph_payload":existing,"input_hash":_hash({"source_lead_id":source_lead_id}),"output_hash":digest,"request":request,"reused":True}
    context={"queue_name":queue.name,"source_lead_id":source_lead_id,"status":queue.status}
    payload=fetch_lead(source_lead_id,get_meta_settings(),context)
    digest=_hash(payload)
    values={"graph_payload":safe_json_dumps(payload),"graph_api_response":safe_json_dumps(payload),"graph_api_request":safe_json_dumps(request),"graph_payload_hash":digest}
    # Task 1: clear any stale error fields left by a previous failed attempt.
    # Only cleared after a confirmed successful primary fetch.
    _clear_graph_error_fields(values)
    set_values("Lead Intake Queue",queue.name,values)
    _sync_webhook_event(queue,{"graph_api_request":values["graph_api_request"],"graph_api_response":values["graph_api_response"],"queue_status":"Lead Downloaded"})
    return {"graph_payload":payload,"input_hash":_hash({"source_lead_id":source_lead_id}),"output_hash":digest,"request":request,"reused":False}

def _recover_source_lead_id(queue):
    if has_field("Lead Intake Queue","meta_webhook_event") and queue.get("meta_webhook_event"):
        evt_id=frappe.db.get_value("Meta Webhook Event",queue.meta_webhook_event,"leadgen_id")
        if evt_id and str(evt_id).strip().lower() not in ("none", "null", "0", ""):
            candidate=str(evt_id)
            # Never recover a synthetic/internal ID — it cannot be used as a Graph leadgen ID.
            if not is_synthetic_leadgen_id(candidate):
                return candidate
    payload=load_json(getattr(queue,"raw_payload",None),{})
    if isinstance(payload,dict):
        for key in ("source_lead_id","leadgen_id","lead_id"):
            val=payload.get(key) or (payload.get("value") or {}).get(key)
            if val and str(val).strip().lower() not in ("none", "null", "0", ""):
                candidate=str(val)
                if not is_synthetic_leadgen_id(candidate):
                    return candidate
    return None

def graph_failure(queue_name,claim,exc,traceback):
    request=getattr(exc,"request",None) or _graph_request(frappe.db.get_value("Lead Intake Queue",queue_name,"source_lead_id"))
    response=getattr(exc,"response",None)
    values={"graph_api_request":safe_json_dumps(request),"graph_api_response":safe_json_dumps(response) if response is not None else None}
    values.update(_graph_error_values(response,getattr(exc,"status_code",None),str(exc)))
    set_values("Lead Intake Queue",queue_name,values)
    queue=frappe.get_doc("Lead Intake Queue",queue_name)
    _sync_webhook_event(queue,{"graph_api_request":values.get("graph_api_request"),"graph_api_response":values.get("graph_api_response"),"queue_status":"Needs Retry"})
    if getattr(exc, "permanent", False) and claim:
        stage_doc_name = getattr(claim, "name", None)
        if stage_doc_name:
            current_attempts = frappe.db.get_value("Lead Intake Stage", stage_doc_name, "attempt_count") or 1
            frappe.db.set_value("Lead Intake Stage", stage_doc_name, {"max_attempts": current_attempts, "next_retry_at": None}, update_modified=False)
        # Task 4: when the Graph failure is permanent AND there is no durable customer
        # evidence that would allow NORMALIZE to reconstruct meaningful lead data,
        # cascade the permanent failure to NORMALIZE (and thereby CLASSIFICATION,
        # CUSTOMER360, CRM_LEAD ...) by marking NORMALIZE as SKIPPED with a clear reason.
        # This prevents the queue being silently stuck forever waiting for a stage that
        # can never produce useful data.
        # If custom_answers or any PII field already exists on the queue, NORMALIZE can
        # still attempt reconstruction from that durable evidence — do not cascade in
        # that case.
        _cascade_permanent_graph_failure_if_no_evidence(queue_name, queue, str(exc))

def normalize(queue_name,claim=None):
    queue=frappe.get_doc("Lead Intake Queue",queue_name)
    graph_payload=_successful_graph_payload(queue)
    existing=load_json(getattr(queue,"normalized_payload",None),{})
    graph_hash=getattr(queue,"graph_payload_hash",None) or (_hash(graph_payload) if graph_payload else None)
    has_pii=bool(existing and (existing.get("customer_name") or existing.get("phone") or existing.get("email")))
    is_valid_reuse=bool(existing and getattr(queue,"normalized_payload_hash",None) and getattr(queue,"normalization_version",None)==MAPPING_VERSION)
    if is_valid_reuse:
        if not graph_payload or (has_pii and getattr(queue,"graph_payload_hash",None)==graph_hash):
            return {"normalized":existing,"input_hash":graph_hash or _hash(existing),"output_hash":queue.normalized_payload_hash,"reused":True}
    if not graph_payload:
        return _rebuild_normalized(queue_name,queue=queue,reason="normalize_stage_recovery")
    context={"queue_name":queue.name,"source_lead_id":queue.source_lead_id,"status":queue.status}
    data=normalize_lead(graph_payload,get_meta_settings(),context)
    return _persist_normalized(queue,data,graph_hash,reason="graph_normalization")

def load_normalized(queue_name):
    data=load_json(frappe.db.get_value("Lead Intake Queue",queue_name,"normalized_payload"),{})
    has_pii=bool(data and (data.get("customer_name") or data.get("phone") or data.get("email")))
    if data and (has_pii or not _successful_graph_payload(frappe.get_doc("Lead Intake Queue",queue_name))):
        return data
    return _rebuild_normalized(queue_name,reason="consumer_recovery")["normalized"]

def _rebuild_normalized(queue_name,queue=None,reason="recovery"):
    queue=queue or frappe.get_doc("Lead Intake Queue",queue_name)
    graph_payload=_successful_graph_payload(queue)
    if graph_payload:
        graph_hash=getattr(queue,"graph_payload_hash",None) or _hash(graph_payload)
        data=normalize_lead(graph_payload,get_meta_settings(),{"queue_name":queue.name,"source_lead_id":queue.source_lead_id,"status":queue.status})
    else:
        graph_payload=_graph_payload_from_queue(queue)
        if not graph_payload:
            raise ValueError(f"Normalized payload is missing for queue {queue_name} and durable reconstruction evidence is unavailable")
        graph_hash=getattr(queue,"graph_payload_hash",None) or _hash(graph_payload)
        data=normalize_lead(graph_payload,get_meta_settings(),{"queue_name":queue.name,"source_lead_id":queue.source_lead_id,"status":queue.status})
    _merge_queue_evidence(data,queue)
    result=_persist_normalized(queue,data,graph_hash,reason=reason)
    log_info("normalized_payload_rebuilt",queue_name=queue.name,source_lead_id=queue.source_lead_id,reason=reason,graph_snapshot=bool(_successful_graph_payload(queue)),output_hash=result["output_hash"])
    return result

def _persist_normalized(queue,data,graph_hash,reason):
    _merge_queue_evidence(data,queue)
    digest=_hash(data)
    values={field:data.get(field) for field in ("source_lead_id","customer_name","phone","email","country_interested","visa_type","campaign_name","campaign_id","adset_name","adset_id","ad_name","ad_id","page_id","form_id")}
    values.update({"status":"Lead Downloaded","custom_answers":safe_json_dumps(data.get("custom_answers") or {}),"normalized_payload":safe_json_dumps(data),"normalized_payload_hash":digest,"normalization_version":MAPPING_VERSION,"graph_payload_hash":graph_hash})
    set_values("Lead Intake Queue",queue.name,values)
    _sync_webhook_event(queue,{"queue_status":"Lead Downloaded"})
    res_dict={"normalized":data,"input_hash":graph_hash,"output_hash":digest,"reused":False,"recovered":reason!="graph_normalization"}
    stage_name=f"{queue.name}:NORMALIZE"
    if frappe.db.exists("Lead Intake Stage",stage_name):
        current_state = frappe.db.get_value("Lead Intake Stage", stage_name, "state")
        if current_state != "RUNNING":
            frappe.db.set_value("Lead Intake Stage",stage_name,{"result_json":safe_json_dumps(res_dict),"output_hash":digest},update_modified=False)
    return res_dict

def _merge_queue_evidence(data,queue):
    answers=load_json(getattr(queue,"custom_answers",None),{})
    if isinstance(answers,dict):
        data["custom_answers"]={**answers,**(data.get("custom_answers") or {})}
        data["meta_fields"]={**answers,**(data.get("meta_fields") or {})}
    for field in ("source_lead_id","customer_name","phone","email","country_interested","visa_type","campaign_name","campaign_id","adset_name","adset_id","ad_name","ad_id","page_id","form_id"):
        if not data.get(field) and getattr(queue,field,None):
            data[field]=getattr(queue,field)

def _graph_payload_from_queue(queue):
    answers=load_json(getattr(queue,"custom_answers",None),{})
    fields=[]
    if isinstance(answers,dict):
        for name,value in answers.items():
            if value is None or value=="":
                continue
            fields.append({"name":name,"values":value if isinstance(value,list) else [value]})
    if not fields:
        for name in ("customer_name","phone","email","country_interested","visa_type"):
            value=getattr(queue,name,None)
            if value:
                fields.append({"name":name,"values":[value]})
    raw=load_json(getattr(queue,"raw_payload",None),{})
    lead_id=getattr(queue,"source_lead_id",None) or (raw.get("leadgen_id") if isinstance(raw,dict) else None)
    if not fields and not lead_id and not (isinstance(raw,dict) and (raw.get("page_id") or raw.get("form_id"))):
        return None
    # Task 3: require at least some useful customer/lead field data for reconstruction.
    # An ID alone (without any customer PII or form answers) is NOT sufficient evidence
    # to produce a meaningful normalized payload. Returning a minimal skeleton would
    # allow empty Customers/Leads to be created silently.
    if not fields:
        return None
    payload={"id":lead_id,"field_data":fields}
    for field in ("form_id","page_id","campaign_id","campaign_name","adset_id","adset_name","ad_id","ad_name"):
        value=getattr(queue,field,None) or (raw.get(field) if isinstance(raw,dict) else None)
        if value:
            payload[field]=value
    return payload

def customer360(queue_name,claim=None):
    data=load_normalized(queue_name)
    context=_context(queue_name,data)
    customer=resolve_customer(data,context)
    set_values("Lead Intake Queue",queue_name,{"matched_customer":customer,"status":"Customer Matched"})
    return {"customer":customer,"result_doctype":"Customer","result_name":customer,"input_hash":frappe.db.get_value("Lead Intake Queue",queue_name,"normalized_payload_hash"),"output_hash":_hash({"customer":customer})}

def classification(queue_name,claim=None):
    return classify_queue(queue_name,claim=claim)

def crm_lead(queue_name,claim=None):
    data=load_normalized(queue_name)
    customer=frappe.db.get_value("Lead Intake Queue",queue_name,"matched_customer")
    if not customer or not frappe.db.exists("Customer",customer):
        raise ValueError("Customer360 stage has no durable Customer")
    context=_context(queue_name,data)
    lead=resolve_lead(data,customer,context)
    classification_values=frappe.db.get_value("Lead Intake Queue",queue_name,["lead_category","lead_group","responsible_department","classification_source","classification_status","classification_rule","classification_reason","classified_at","classified_by"],as_dict=True) or {}
    sync_lead_classification(lead,classification_values,overwrite_automatic=False)
    set_values("Lead Intake Queue",queue_name,{"matched_customer":customer,"matched_lead":lead,"status":"Lead Created"})
    _sync_webhook_event(frappe.get_doc("Lead Intake Queue",queue_name),{"queue_status":"Lead Created","crm_lead":lead,"customer":customer})
    return {"lead":lead,"customer":customer,"result_doctype":"CRM Lead","result_name":lead,"input_hash":frappe.db.get_value("Lead Intake Queue",queue_name,"normalized_payload_hash"),"output_hash":_hash({"lead":lead,"customer":customer})}

def lead_workflow(queue_name,claim=None):
    queue=_business_context(queue_name)
    context=_context(queue_name,queue.data)
    mark_lead_stage(queue.lead,"Lead",context)
    qualify_lead(queue.lead,context)
    deal=create_deal_if_supported(queue.lead,queue.data)
    return {"lead":queue.lead,"deal":deal,"result_doctype":"CRM Lead","result_name":queue.lead,"output_hash":_hash({"lead":queue.lead,"deal":deal})}

def visa_application(queue_name,claim=None):
    queue=_business_context(queue_name)
    visa=create_for_lead(queue.lead,queue.customer,queue.data,queue_name=queue_name)
    set_values("Lead Intake Queue",queue_name,{"visa_application":visa})
    _sync_webhook_event(frappe.get_doc("Lead Intake Queue",queue_name),{"visa_application":visa})
    return {"visa_application":visa,"result_doctype":"Visa Application","result_name":visa,"output_hash":_hash({"visa_application":visa})}

def communication_event(queue_name,claim=None):
    queue=_business_context(queue_name)
    lead_id=queue.data.get("source_lead_id") or queue.queue.get("source_lead_id")
    if not lead_id or str(lead_id).strip().lower() in ("none","null",""):
        raise ValueError(f"Cannot generate Communication Event idempotency key: invalid source_lead_id in queue '{queue_name}'")
    event_id=f"meta:lead:{lead_id}"
    legacy_event_id=f"meta:{lead_id}"
    attribution={"campaign_id":queue.data.get("campaign_id"),"campaign_name":queue.data.get("campaign_name"),"adset_id":queue.data.get("adset_id"),"adset_name":queue.data.get("adset_name"),"ad_id":queue.data.get("ad_id"),"ad_name":queue.data.get("ad_name"),"page_id":queue.data.get("page_id"),"form_id":queue.data.get("form_id"),"lead_id":lead_id}
    timeline={"webhook":str(queue.queue.creation),"graph":str(queue.queue.get("processing_started_at") or ""),"communication":now()}
    values={"event_id":event_id,"source":"Meta Form","source_channel":"Meta Lead Ads","event_type":"Lead","direction":"Inbound","customer":queue.customer,"customer360":queue.customer,"lead":queue.lead,"visa_application":queue.visa,"phone":queue.data.get("phone"),"email":queue.data.get("email"),"content":safe_json_dumps(queue.data.get("custom_answers")),"summary":f"Meta Lead Ads intake for {queue.data.get('customer_name') or queue.data.get('phone') or queue.data.get('email')}","event_datetime":now(),"channel_id":queue_name,"conversation_id":event_id,"lead_intake_queue":queue_name,"meta_campaign_name":queue.data.get("campaign_name"),"meta_campaign_id":queue.data.get("campaign_id"),"meta_adset_name":queue.data.get("adset_name"),"meta_adset_id":queue.data.get("adset_id"),"meta_ad_name":queue.data.get("ad_name"),"meta_ad_id":queue.data.get("ad_id"),"facebook_page_id":queue.data.get("page_id"),"facebook_form_id":queue.data.get("form_id"),"facebook_lead_id":lead_id,"original_normalized_payload":queue.queue.get("normalized_payload"),"meta_attribution_json":safe_json_dumps(attribution),"processing_timeline":safe_json_dumps(timeline)}
    existing=(
        frappe.db.get_value("Communication Event",{"event_id":event_id},"name")
        or frappe.db.get_value("Communication Event",{"event_id":legacy_event_id},"name")
        or (has_field("Communication Event","facebook_lead_id") and lead_id and frappe.db.get_value("Communication Event",{"facebook_lead_id":lead_id},"name"))
    )
    if existing:
        event=existing
        current=frappe.db.get_value("Communication Event",event,[field for field in values if has_field("Communication Event",field)],as_dict=True) or {}
        missing={field:value for field,value in values.items() if value is not None and has_field("Communication Event",field) and not current.get(field)}
        if missing:
            frappe.db.set_value("Communication Event",event,missing,update_modified=False)
    else:
        doc=frappe.new_doc("Communication Event")
        for field,value in values.items():
            if doc.meta.has_field(field):
                doc.set(field,value)
        try:
            doc.insert(ignore_permissions=True)
            event=doc.name
        except frappe.DuplicateEntryError:
            event=(
                frappe.db.get_value("Communication Event",{"event_id":event_id},"name")
                or frappe.db.get_value("Communication Event",{"event_id":legacy_event_id},"name")
            )
            if not event:
                raise
    set_values("Lead Intake Queue",queue_name,{"communication_event":event})
    _sync_webhook_event(frappe.get_doc("Lead Intake Queue",queue_name),{"communication_event":event})
    return {"communication_event":event,"result_doctype":"Communication Event","result_name":event,"output_hash":_hash({"communication_event":event})}

def follow_up(queue_name,claim=None):
    queue=_business_context(queue_name)
    todo=create_meta_followup(queue.data,queue.lead,queue.customer,None,queue_name,_context(queue_name,queue.data))
    set_values("Lead Intake Queue",queue_name,{"followup_reference":todo})
    event=queue.queue.get("communication_event")
    if event and frappe.db.exists("Communication Event",event) and has_field("Communication Event","followup_reference") and not frappe.db.get_value("Communication Event",event,"followup_reference"):
        frappe.db.set_value("Communication Event",event,"followup_reference",todo,update_modified=False)
    return {"followup":todo,"result_doctype":"ToDo","result_name":todo,"output_hash":_hash({"followup":todo})}

def counselor_assignment(queue_name,claim=None):
    queue=_business_context(queue_name)
    try:
        employee=assign_lead(queue.lead,queue.queue,context=_context(queue_name,queue.data),communication_event=queue.queue.get("communication_event"))
    except NotApplicable as exc:
        # Unsupported department: mark stage SKIPPED, do NOT fail pipeline
        record(queue=queue_name,stage="COUNSELOR_ASSIGNMENT",execution_type="Stage",result="SKIPPED",details={"reason":str(exc)})
        if has_field("CRM Lead","assignment_status"):
            frappe.db.set_value("CRM Lead",queue.lead,"assignment_status","Not Applicable",update_modified=False)
        return {"employee":None,"assignment_type":"NOT_APPLICABLE","result_doctype":None,"result_name":None,"output_hash":_hash({"not_applicable":str(exc)})}
    if not employee:
        raise NoEligibleCounselor("No eligible counselor found for the department")
    set_values("Lead Intake Queue",queue_name,{"assigned_employee":employee})
    _set_assignment_status(queue.lead,"Assigned")
    if has_field("CRM Lead","assigned_counselor"):
        frappe.db.set_value("CRM Lead",queue.lead,"assigned_counselor",employee,update_modified=False)
    event=queue.queue.get("communication_event")
    if event and frappe.db.exists("Communication Event",event) and has_field("Communication Event","employee") and not frappe.db.get_value("Communication Event",event,"employee"):
        frappe.db.set_value("Communication Event",event,"employee",employee,update_modified=False)
    return {"employee":employee,"assignment_type":"Automatic Round Robin","result_doctype":"Employee","result_name":employee,"output_hash":_hash({"employee":employee})}

def assignment_failure(queue_name,claim,exc,traceback):
    lead=frappe.db.get_value("Lead Intake Queue",queue_name,"matched_lead")
    if lead and frappe.db.exists("CRM Lead",lead):
        _set_assignment_status(lead,"Needs Assignment")

def ai_dispatch(queue_name,claim=None):
    queue=frappe.get_doc("Lead Intake Queue",queue_name)
    event=queue.get("communication_event")
    if not event or not frappe.db.exists("Communication Event",event):
        raise ValueError("Communication Event is required before AI dispatch")
    key=_ai_key(event)
    if not frappe.db.exists("Lead Intake AI Job",key):
        doc=frappe.new_doc("Lead Intake AI Job")
        doc.update({"idempotency_key":key,"queue":queue_name,"communication_event":event,"pipeline_version":1,"state":"PENDING","attempt_count":0})
        doc.insert(ignore_permissions=True,ignore_if_duplicate=True)
    set_values("Lead Intake Queue",queue_name,{"ai_status":"Pending","ai_error":"","ai_traceback":""})
    return {"communication_event":event,"ai_job":key,"ai_status":"Pending","result_doctype":"Lead Intake AI Job","result_name":key,"output_hash":_hash({"event":event,"pipeline":"ai"})}

def ai_dispatch_failure(queue_name,claim,exc,traceback):
    current=frappe.db.get_value("Lead Intake Queue",queue_name,"ai_retry_count") if has_field("Lead Intake Queue","ai_retry_count") else 0
    set_values("Lead Intake Queue",queue_name,{"ai_status":"Failed","ai_error":str(exc),"ai_traceback":traceback,"ai_retry_count":(current or 0)+1})

def dispatch_ai_job(queue_name):
    if not frappe.db.exists("Lead Intake AI Job",{"queue":queue_name}):
        return None
    job=frappe.db.get_value("Lead Intake AI Job",{"queue":queue_name},["name","communication_event","state","next_retry_at","lease_expires_at"],as_dict=True)
    now_dt=now_datetime()
    if not job or job.state in ("QUEUED","RUNNING","COMPLETED") or job.next_retry_at and get_datetime(job.next_retry_at)>now_dt or job.lease_expires_at and get_datetime(job.lease_expires_at)>now_dt:
        return job
    token=uuid.uuid4().hex
    owner=f"{frappe.local.site or 'site'}:{socket.gethostname()}:{os.getpid()}"
    expires=add_to_date(now_dt,minutes=5)
    frappe.db.sql("""update `tabLead Intake AI Job` set lease_owner=%s,lease_token=%s,lease_expires_at=%s,heartbeat_at=%s,attempt_count=attempt_count+1,modified=%s where name=%s and state in ('PENDING','FAILED') and (next_retry_at is null or next_retry_at<=%s) and (lease_expires_at is null or lease_expires_at<=%s)""",(owner,token,expires,now_dt,now_dt,job.name,now_dt,now_dt))
    if frappe.db._cursor.rowcount!=1:
        frappe.db.rollback()
        return job
    frappe.db.commit()
    try:
        queued=frappe.enqueue("visa_crm.api.ai_intelligence.process_communication_ai",queue="long",job_name=job.name,enqueue_after_commit=False,event_name=job.communication_event,queue_name=queue_name,ai_job_name=job.name)
        rq_id=getattr(queued,"id",None) or getattr(queued,"job_id",None)
        frappe.db.sql("""update `tabLead Intake AI Job` set state='QUEUED',job_id=%s,queued_at=%s,next_retry_at=null,lease_owner=null,lease_token=null,lease_expires_at=null,last_error_class=null,last_error=null,last_traceback=null,modified=%s where name=%s and lease_token=%s and state in ('PENDING','FAILED')""",(rq_id,now_dt,now_dt,job.name,token))
        state="QUEUED" if frappe.db._cursor.rowcount==1 else frappe.db.get_value("Lead Intake AI Job",job.name,"state")
        set_values("Lead Intake Queue",queue_name,{"ai_status":{"RUNNING":"Running","COMPLETED":"Completed","FAILED":"Failed"}.get(state,"Queued"),"ai_error":"","ai_traceback":""})
        _append_ai_retry_history(job.name,{"at":str(now_dt),"attempt":frappe.db.get_value("Lead Intake AI Job",job.name,"attempt_count"),"result":"QUEUED","job_id":rq_id})
        record(queue=queue_name,stage="AI_DISPATCH",execution_type="AI Retry",result="SUCCESS",retry_count=frappe.db.get_value("Lead Intake AI Job",job.name,"attempt_count"),details={"ai_job":job.name,"rq_job_id":rq_id})
        frappe.db.commit()
        return frappe.db.get_value("Lead Intake AI Job",job.name,["name","state","job_id"],as_dict=True)
    except Exception as exc:
        traceback=frappe.get_traceback()
        frappe.db.rollback()
        attempt=frappe.db.get_value("Lead Intake AI Job",job.name,"attempt_count") or 1
        retry_at=ai_retry_at(attempt,now_datetime())
        frappe.db.set_value("Lead Intake AI Job",job.name,{"state":"FAILED","next_retry_at":retry_at,"lease_owner":None,"lease_token":None,"lease_expires_at":None,"last_error_class":f"{type(exc).__module__}.{type(exc).__qualname__}","last_error":str(exc),"last_traceback":traceback},update_modified=False)
        current=frappe.db.get_value("Lead Intake Queue",queue_name,"ai_retry_count") or 0
        set_values("Lead Intake Queue",queue_name,{"ai_status":"Failed","ai_error":str(exc),"ai_traceback":traceback,"ai_retry_count":current+1})
        _append_ai_retry_history(job.name,{"at":str(now_datetime()),"attempt":attempt,"result":"FAILED","error":str(exc),"next_retry_at":str(retry_at)})
        record(queue=queue_name,stage="AI_DISPATCH",execution_type="AI Retry",result="FAILED",retry_count=attempt,failure_reason=str(exc),next_retry=retry_at,traceback=traceback,details={"ai_job":job.name})
        frappe.db.commit()
        frappe.logger("visa_crm.ai").error(safe_json_dumps({"event":"ai_dispatch_failed","queue":queue_name,"ai_job":job.name,"error":str(exc),"traceback":traceback}))
        return frappe.db.get_value("Lead Intake AI Job",job.name,["name","state","next_retry_at","last_error"],as_dict=True)

def recover_stale_ai_jobs(at=None):
    if not frappe.db.exists("DocType","Lead Intake AI Job"):
        return 0
    at=get_datetime(at or now_datetime())
    cutoff=add_to_date(at,minutes=-max(int(frappe.conf.get("visa_crm_ai_stale_minutes") or 60),15))
    rows=frappe.get_all("Lead Intake AI Job",filters={"state":["in",["QUEUED","RUNNING"]]},fields=["name","queue","state","queued_at","heartbeat_at"])
    recovered=0
    for row in rows:
        stage_state=frappe.db.get_value("Lead Intake Stage",f"{row.queue}:AI_GEMINI","state") if frappe.db.exists("DocType","Lead Intake Stage") else None
        stale=row.state=="QUEUED" and row.queued_at and get_datetime(row.queued_at)<=cutoff or row.state=="RUNNING" and (stage_state=="FAILED" or row.heartbeat_at and get_datetime(row.heartbeat_at)<=cutoff)
        if not stale:
            continue
        frappe.db.set_value("Lead Intake AI Job",row.name,{"state":"FAILED","next_retry_at":at,"lease_owner":None,"lease_token":None,"lease_expires_at":None,"last_error_class":"AIWorkerLeaseExpired","last_error":"AI worker did not complete before the stale timeout"},update_modified=False)
        set_values("Lead Intake Queue",row.queue,{"ai_status":"Failed","ai_error":"AI worker did not complete before the stale timeout"})
        _append_ai_retry_history(row.name,{"at":str(at),"result":"RECOVERED","error":"AI worker stale timeout","next_retry_at":str(at)})
        record(queue=row.queue,stage="AI_GEMINI",execution_type="Worker Restart",result="RECOVERED",failure_reason="AI worker did not complete before the stale timeout",next_retry=at,details={"ai_job":row.name})
        recovered+=1
    if recovered:
        frappe.db.commit()
    return recovered

def _ai_key(event):
    return f"ai:{event}:1"

def ai_retry_at(attempt,at=None,error_str=None):
    at=at or now_datetime()
    err_msg=str(error_str or "").lower()
    
    # 1. Permanent Auth / Configuration Failures
    if any(k in err_msg for k in ("401", "403", "invalid api key", "not configured", "unauthorized", "forbidden")):
        return None

    # 2. Parse provider retry delay if present
    parsed_delay=None
    if error_str:
        import re
        m1=re.search(r'"retryDelay"\s*:\s*"(\d+)s?"',str(error_str))
        if m1:
            parsed_delay=int(m1.group(1))
        else:
            m2=re.search(r'Please retry in\s+([0-9\.]+)\s*s',str(error_str),re.IGNORECASE)
            if m2:
                parsed_delay=int(float(m2.group(1)))

    # 3. 429 Quota / Rate Limit Errors
    is_quota_error=bool(any(k in err_msg for k in ("429","resource_exhausted","quota","rate limit")))
    is_daily_quota=bool(any(k in err_msg for k in ("free_tier_requests", "requestsperday", "daily", "per day", "quota exceeded")))
    
    if is_quota_error:
        if is_daily_quota:
            seconds=max(parsed_delay or 3600, 3600)
        else:
            seconds=max(parsed_delay or 120, 60)
    elif parsed_delay:
        seconds=max(parsed_delay, 60)
    elif any(k in err_msg for k in ("500", "502", "503", "504", "server error", "timeout")):
        delays=(60, 300, 900, 1800, 3600)
        seconds=delays[cint(attempt)-1] if 1<=cint(attempt)<=len(delays) else 3600
    else:
        delays=(30,120,300,600,1800)
        seconds=delays[cint(attempt)-1] if 1<=cint(attempt)<=len(delays) else 3600

    return add_to_date(at,seconds=seconds)

def _append_ai_retry_history(job_name,item):
    if not has_field("Lead Intake AI Job","retry_history_json"):
        return
    history=load_json(frappe.db.get_value("Lead Intake AI Job",job_name,"retry_history_json"),[])
    if not isinstance(history,list):
        history=[]
    history.append(item)
    frappe.db.set_value("Lead Intake AI Job",job_name,"retry_history_json",safe_json_dumps(history[-200:]),update_modified=False)

def _successful_graph_payload(queue):
    for field in ("graph_payload","graph_api_response"):
        data=load_json(getattr(queue,field,None),{})
        if data and not data.get("error") and (data.get("id") or data.get("field_data")):
            return data
    if frappe.db.exists("DocType","Lead Intake Stage"):
        stage_name=f"{queue.name}:GRAPH_DOWNLOAD"
        res_json=frappe.db.get_value("Lead Intake Stage",stage_name,"result_json")
        if res_json:
            res_data=load_json(res_json,{})
            graph=res_data.get("graph_payload") or res_data.get("result")
            if isinstance(graph,dict) and not graph.get("error") and (graph.get("id") or graph.get("field_data")):
                return graph
    return None

def _graph_request(source_lead_id):
    return {"url":f"https://graph.facebook.com/{GRAPH_VERSION}/{source_lead_id}","path":str(source_lead_id or ""),"params":{"fields":LEAD_FIELDS}}

def _graph_error_values(response,status_code,message):
    error=(response or {}).get("error",{}) if isinstance(response,dict) else {}
    return {"graph_http_status":error.get("http_status") or status_code,"graph_fbtrace_id":error.get("fbtrace_id"),"graph_error_code":error.get("code"),"graph_error_subcode":error.get("error_subcode") or error.get("subcode"),"graph_error_type":error.get("type"),"graph_error_message":error.get("message") or message}

# Fields that record Graph failure detail.  On a successful fetch these must be
# cleared so that operators and monitors see only the current outcome, not stale
# state from a previous failed attempt.
_GRAPH_ERROR_FIELDS=("graph_error_code","graph_error_subcode","graph_error_message","graph_error_type","graph_fbtrace_id","graph_http_status")

def _clear_graph_error_fields(values):
    """Merge null-values for all graph error fields into *values*.

    Called only on the success path of graph_download().  The caller passes the
    dict that is about to be written to the Lead Intake Queue so all changes are
    committed in a single set_values() call, avoiding a separate DB round-trip.

    Only clears fields that actually exist on the DocType so the function is safe
    to call regardless of schema version.
    """
    meta=frappe.get_meta("Lead Intake Queue")
    for field in _GRAPH_ERROR_FIELDS:
        if meta.has_field(field):
            values[field]=None


def _set_if_blank(doctype_name,values):
    current=frappe.db.get_value("Lead Intake Queue",doctype_name,list(values),as_dict=True) or {}
    set_values("Lead Intake Queue",doctype_name,{field:value for field,value in values.items() if value is not None and not current.get(field)})

def _sync_webhook_event(queue,values):
    if not has_field("Lead Intake Queue","meta_webhook_event") or not queue.get("meta_webhook_event"):
        return
    set_values("Meta Webhook Event",queue.meta_webhook_event,{field:value for field,value in values.items() if value is not None})

def _hash(value):
    payload=json.dumps(value,default=str,ensure_ascii=False,separators=(",",":"),sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def _context(queue_name,data):
    return {"queue_name":queue_name,"source_lead_id":data.get("source_lead_id"),"status":frappe.db.get_value("Lead Intake Queue",queue_name,"status")}

def _business_context(queue_name):
    queue=frappe.get_doc("Lead Intake Queue",queue_name)
    data=load_normalized(queue_name)
    lead=queue.get("matched_lead")
    customer=queue.get("matched_customer")
    if not lead or not frappe.db.exists("CRM Lead",lead):
        raise ValueError("CRM Lead stage has no durable Lead")
    if not customer or not frappe.db.exists("Customer",customer):
        raise ValueError("Customer360 stage has no durable Customer")
    visa=queue.get("visa_application")
    return frappe._dict({"queue":queue,"data":data,"lead":lead,"customer":customer,"visa":visa})

def _set_assignment_status(lead,status):
    if has_field("CRM Lead","assignment_status"):
        frappe.db.set_value("CRM Lead",lead,"assignment_status",status,update_modified=False)

def _cascade_permanent_graph_failure_if_no_evidence(queue_name,queue,error_message):
    """Skip NORMALIZE (and thereby all dependent stages) when GRAPH_DOWNLOAD has
    failed permanently AND there is no durable customer evidence on the queue.

    When there IS useful evidence (custom_answers, PII fields already stored),
    NORMALIZE can still reconstruct meaningful data from the queue record alone
    — so we do NOT cascade in that case.

    The Skip is only applied to NORMALIZE; the rollup_queue() BLOCKED logic
    propagates the terminal state to CLASSIFICATION, CUSTOMER360 etc. automatically.
    """
    from visa_crm.api.pipeline_engine import skip_stage,STAGE_BY_NAME
    # Check whether there is any durable customer evidence on the queue.
    queue_rec=frappe.db.get_value(
        "Lead Intake Queue",queue_name,
        ["custom_answers","customer_name","phone","email"],as_dict=True
    ) or {}
    answers=load_json(queue_rec.get("custom_answers"),{})
    has_custom_answers=bool(isinstance(answers,dict) and answers)
    has_pii=bool(queue_rec.get("customer_name") or queue_rec.get("phone") or queue_rec.get("email"))
    if has_custom_answers or has_pii:
        # Durable evidence exists; NORMALIZE may still attempt reconstruction.
        log_info(
            "graph_permanent_failure_reconstruction_possible",
            queue_name=queue_name,
            has_custom_answers=has_custom_answers,
            has_pii=has_pii,
        )
        return
    # No evidence: mark NORMALIZE skipped so dependent stages become BLOCKED
    # by rollup_queue() rather than silently waiting forever.
    reason=(f"GRAPH_DOWNLOAD failed permanently with no durable reconstruction "
            f"evidence on queue {queue_name}. "
            f"Graph error: {error_message[:200]}.")
    try:
        # Only skip when NORMALIZE is still NOT_STARTED or BLOCKED
        norm_stage_name=f"{queue_name}:NORMALIZE"
        norm_state=frappe.db.get_value("Lead Intake Stage",norm_stage_name,"state")
        if norm_state not in ("NOT_STARTED","BLOCKED",None):
            return
        # skip_stage() requires requirement_class=Optional, so we set directly.
        frappe.db.set_value(
            "Lead Intake Stage",norm_stage_name,
            {"state":"FAILED","last_error_class":"PermanentGraphFailure","last_error":reason,"completed_at":now_datetime(),
             "next_retry_at":None,"lease_owner":None,"lease_token":None,"lease_expires_at":None},
            update_modified=False
        )
        log_info(
            "graph_permanent_failure_normalize_skipped",
            queue_name=queue_name,
            reason=reason,
        )
    except Exception as skip_exc:
        # Non-fatal: cascade skip is best-effort. The pipeline will remain stuck
        # for this queue but no data is corrupted.
        log_info("graph_permanent_failure_cascade_skip_error",queue_name=queue_name,error=str(skip_exc))
