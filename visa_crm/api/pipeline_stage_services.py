import hashlib
import json
import frappe
from visa_crm.api.meta_graph import GRAPH_VERSION,LEAD_FIELDS,fetch_lead
from visa_crm.api.meta_mapping import MAPPING_VERSION,normalize_lead
from visa_crm.api.meta_utils import get_meta_settings,has_field,load_json,safe_json_dumps,set_values
from visa_crm.api.customer360 import resolve_customer,resolve_lead

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
    if not graph_payload:
        raise ValueError("Graph payload is missing; NORMALIZE cannot run")
    graph_hash=getattr(queue,"graph_payload_hash",None) or _hash(graph_payload)
    existing=load_json(getattr(queue,"normalized_payload",None),{})
    if existing and getattr(queue,"normalized_payload_hash",None) and getattr(queue,"normalization_version",None)==MAPPING_VERSION:
        return {"normalized":existing,"input_hash":graph_hash,"output_hash":queue.normalized_payload_hash,"reused":True}
    context={"queue_name":queue.name,"source_lead_id":queue.source_lead_id,"status":queue.status}
    data=normalize_lead(graph_payload,get_meta_settings(),context)
    data["page_id"]=data.get("page_id") or getattr(queue,"page_id",None)
    data["form_id"]=data.get("form_id") or getattr(queue,"form_id",None)
    digest=_hash(data)
    values={field:data.get(field) for field in ("source_lead_id","customer_name","phone","email","country_interested","visa_type","campaign_name","campaign_id","adset_name","adset_id","ad_name","ad_id","page_id","form_id")}
    values.update({"status":"Lead Downloaded","custom_answers":safe_json_dumps(data.get("custom_answers") or {}),"normalized_payload":safe_json_dumps(data),"normalized_payload_hash":digest,"normalization_version":MAPPING_VERSION,"graph_payload_hash":graph_hash})
    set_values("Lead Intake Queue",queue.name,values)
    _sync_webhook_event(queue,{"queue_status":"Lead Downloaded"})
    return {"normalized":data,"input_hash":graph_hash,"output_hash":digest,"reused":False}

def load_normalized(queue_name):
    data=load_json(frappe.db.get_value("Lead Intake Queue",queue_name,"normalized_payload"),{})
    if not data:
        raise ValueError(f"Normalized payload is missing for queue {queue_name}")
    return data

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
