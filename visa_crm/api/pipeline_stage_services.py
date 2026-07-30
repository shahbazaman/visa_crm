import hashlib
import json
import os
import socket
import uuid
import frappe
from frappe.utils import add_to_date,get_datetime,now,now_datetime
from visa_crm.api.meta_graph import GRAPH_VERSION,LEAD_FIELDS,fetch_lead
from visa_crm.api.meta_mapping import MAPPING_VERSION,normalize_lead
from visa_crm.api.meta_utils import get_meta_settings,has_field,load_json,log_info,safe_json_dumps,set_values
from visa_crm.api.customer360 import resolve_customer,resolve_lead
from visa_crm.api.followup import create_meta_followup
from visa_crm.api.lead_assignment import assign_lead
from visa_crm.api.visa_application import create_for_lead
from visa_crm.api.workflow import create_deal_if_supported,mark_lead_stage,qualify_lead

class NoEligibleCounselor(RuntimeError):
    pass

def graph_download(queue_name,claim=None):
    queue=frappe.get_doc("Lead Intake Queue",queue_name)
    existing=_successful_graph_payload(queue)
    request=_graph_request(queue.source_lead_id)
    if existing:
        digest=_hash(existing)
        _set_if_blank(queue_name,{"graph_payload_hash":digest,"graph_api_request":safe_json_dumps(request)})
        return {"graph_payload":existing,"input_hash":_hash({"source_lead_id":queue.source_lead_id}),"output_hash":digest,"request":request,"reused":True}
    context={"queue_name":queue.name,"source_lead_id":queue.source_lead_id,"status":queue.status}
    payload=fetch_lead(queue.source_lead_id,get_meta_settings(),context)
    digest=_hash(payload)
    values={"graph_payload":safe_json_dumps(payload),"graph_api_response":safe_json_dumps(payload),"graph_api_request":safe_json_dumps(request),"graph_payload_hash":digest}
    set_values("Lead Intake Queue",queue.name,values)
    _sync_webhook_event(queue,{"graph_api_request":values["graph_api_request"],"graph_api_response":values["graph_api_response"],"queue_status":"Lead Downloaded"})
    return {"graph_payload":payload,"input_hash":_hash({"source_lead_id":queue.source_lead_id}),"output_hash":digest,"request":request,"reused":False}

def graph_failure(queue_name,claim,exc,traceback):
    request=getattr(exc,"request",None) or _graph_request(frappe.db.get_value("Lead Intake Queue",queue_name,"source_lead_id"))
    response=getattr(exc,"response",None)
    values={"graph_api_request":safe_json_dumps(request),"graph_api_response":safe_json_dumps(response) if response is not None else None}
    values.update(_graph_error_values(response,getattr(exc,"status_code",None),str(exc)))
    set_values("Lead Intake Queue",queue_name,values)
    queue=frappe.get_doc("Lead Intake Queue",queue_name)
    _sync_webhook_event(queue,{"graph_api_request":values.get("graph_api_request"),"graph_api_response":values.get("graph_api_response"),"queue_status":"Needs Retry"})

def normalize(queue_name,claim=None):
    queue=frappe.get_doc("Lead Intake Queue",queue_name)
    graph_payload=_successful_graph_payload(queue)
    existing=load_json(getattr(queue,"normalized_payload",None),{})
    if existing and getattr(queue,"normalized_payload_hash",None) and getattr(queue,"normalization_version",None)==MAPPING_VERSION:
        return {"normalized":existing,"input_hash":getattr(queue,"graph_payload_hash",None) or _hash(existing),"output_hash":queue.normalized_payload_hash,"reused":True}
    if not graph_payload:
        return _rebuild_normalized(queue_name,queue=queue,reason="normalize_stage_recovery")
    graph_hash=getattr(queue,"graph_payload_hash",None) or _hash(graph_payload)
    context={"queue_name":queue.name,"source_lead_id":queue.source_lead_id,"status":queue.status}
    data=normalize_lead(graph_payload,get_meta_settings(),context)
    return _persist_normalized(queue,data,graph_hash,reason="graph_normalization")

def load_normalized(queue_name):
    data=load_json(frappe.db.get_value("Lead Intake Queue",queue_name,"normalized_payload"),{})
    return data or _rebuild_normalized(queue_name,reason="consumer_recovery")["normalized"]

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
    return {"normalized":data,"input_hash":graph_hash,"output_hash":digest,"reused":False,"recovered":reason!="graph_normalization"}

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
    if not fields:
        return None
    payload={"id":queue.source_lead_id,"field_data":fields}
    for field in ("form_id","page_id","campaign_id","campaign_name","adset_id","adset_name","ad_id","ad_name"):
        value=getattr(queue,field,None)
        if value:
            payload[field]=value
    return payload

def customer360(queue_name,claim=None):
    data=load_normalized(queue_name)
    context=_context(queue_name,data)
    customer=resolve_customer(data,context)
    set_values("Lead Intake Queue",queue_name,{"matched_customer":customer,"status":"Customer Matched"})
    return {"customer":customer,"result_doctype":"Customer","result_name":customer,"input_hash":frappe.db.get_value("Lead Intake Queue",queue_name,"normalized_payload_hash"),"output_hash":_hash({"customer":customer})}

def crm_lead(queue_name,claim=None):
    data=load_normalized(queue_name)
    customer=frappe.db.get_value("Lead Intake Queue",queue_name,"matched_customer")
    if not customer or not frappe.db.exists("Customer",customer):
        raise ValueError("Customer360 stage has no durable Customer")
    context=_context(queue_name,data)
    lead=resolve_lead(data,customer,context)
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
    event_id=f"meta:{queue.data.get('source_lead_id')}"
    existing=frappe.db.get_value("Communication Event",{"event_id":event_id},"name")
    if existing:
        event=existing
    else:
        doc=frappe.new_doc("Communication Event")
        values={"event_id":event_id,"source":"Meta Form","event_type":"Lead","direction":"Inbound","customer":queue.customer,"lead":queue.lead,"visa_application":queue.visa,"phone":queue.data.get("phone"),"email":queue.data.get("email"),"content":safe_json_dumps(queue.data.get("custom_answers")),"summary":f"Meta Lead Ads intake for {queue.data.get('customer_name') or queue.data.get('phone') or queue.data.get('email')}","event_datetime":now(),"channel_id":queue_name,"lead_intake_queue":queue_name}
        for field,value in values.items():
            if doc.meta.has_field(field):
                doc.set(field,value)
        try:
            doc.insert(ignore_permissions=True)
            event=doc.name
        except frappe.DuplicateEntryError:
            event=frappe.db.get_value("Communication Event",{"event_id":event_id},"name")
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
    employee=assign_lead(queue.lead,queue.queue,context=_context(queue_name,queue.data),communication_event=queue.queue.get("communication_event"))
    if not employee:
        raise NoEligibleCounselor("No eligible counselor is configured for Meta lead assignment")
    set_values("Lead Intake Queue",queue_name,{"assigned_employee":employee})
    _set_assignment_status(queue.lead,"Assigned")
    event=queue.queue.get("communication_event")
    if event and frappe.db.exists("Communication Event",event) and has_field("Communication Event","employee") and not frappe.db.get_value("Communication Event",event,"employee"):
        frappe.db.set_value("Communication Event",event,"employee",employee,update_modified=False)
    return {"employee":employee,"result_doctype":"Employee","result_name":employee,"output_hash":_hash({"employee":employee})}

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
        frappe.db.commit()
        return frappe.db.get_value("Lead Intake AI Job",job.name,["name","state","job_id"],as_dict=True)
    except Exception as exc:
        traceback=frappe.get_traceback()
        frappe.db.rollback()
        retry_at=add_to_date(now_datetime(),minutes=min(60,2**min((frappe.db.get_value("Lead Intake AI Job",job.name,"attempt_count") or 1),6)))
        frappe.db.set_value("Lead Intake AI Job",job.name,{"state":"FAILED","next_retry_at":retry_at,"lease_owner":None,"lease_token":None,"lease_expires_at":None,"last_error_class":f"{type(exc).__module__}.{type(exc).__qualname__}","last_error":str(exc),"last_traceback":traceback},update_modified=False)
        current=frappe.db.get_value("Lead Intake Queue",queue_name,"ai_retry_count") or 0
        set_values("Lead Intake Queue",queue_name,{"ai_status":"Failed","ai_error":str(exc),"ai_traceback":traceback,"ai_retry_count":current+1})
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
        recovered+=1
    if recovered:
        frappe.db.commit()
    return recovered

def _ai_key(event):
    return f"ai:{event}:1"

def _successful_graph_payload(queue):
    for field in ("graph_payload","graph_api_response"):
        data=load_json(getattr(queue,field,None),{})
        if data and not data.get("error") and (data.get("id") or data.get("field_data")):
            return data
    return None

def _graph_request(source_lead_id):
    return {"url":f"https://graph.facebook.com/{GRAPH_VERSION}/{source_lead_id}","path":str(source_lead_id or ""),"params":{"fields":LEAD_FIELDS}}

def _graph_error_values(response,status_code,message):
    error=(response or {}).get("error",{}) if isinstance(response,dict) else {}
    return {"graph_http_status":error.get("http_status") or status_code,"graph_fbtrace_id":error.get("fbtrace_id"),"graph_error_code":error.get("code"),"graph_error_subcode":error.get("error_subcode") or error.get("subcode"),"graph_error_type":error.get("type"),"graph_error_message":error.get("message") or message}

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
