import frappe
from frappe.utils import now_datetime
from visa_crm.api.channel_providers import get_provider
from visa_crm.api.customer360 import match_lead_data
from visa_crm.api.meta_utils import has_doctype, has_field, load_json, normalize_phone, safe_json_dumps, set_if_has

CHANNELS=("whatsapp","messenger","instagram","facebook_page","email","manual_phone","android_call")

def after_communication_insert(doc,method=None):
    attach_context(doc)
    enqueue_ai(doc.name)

def attach_context(doc):
    data={"phone":getattr(doc,"phone",None),"email":getattr(doc,"email",None),"customer_name":getattr(doc,"customer_name",None) or getattr(doc,"contact_person",None)}
    matches=match_lead_data(data,{"event_name":doc.name,"source_lead_id":getattr(doc,"event_id",None),"status":getattr(doc,"status",None)})
    values={}
    if matches.get("customer") and has_field("Communication Event","customer") and not getattr(doc,"customer",None):
        values["customer"]=matches["customer"]
    if matches.get("lead") and has_field("Communication Event","lead") and not getattr(doc,"lead",None):
        values["lead"]=matches["lead"]
    visa=_latest_visa(values.get("lead") or getattr(doc,"lead",None),values.get("customer") or getattr(doc,"customer",None))
    if visa and has_field("Communication Event","visa_application"):
        values["visa_application"]=visa
    if values:
        frappe.db.set_value("Communication Event",doc.name,values,update_modified=False)

def record_interaction(channel,payload,direction="Inbound",assigned_to=None):
    provider=get_provider(channel)
    data=provider.normalize_inbound(payload or {})
    event_id=data.get("provider_message_id") or f"{data.get('provider')}:{frappe.generate_hash(length=12)}"
    existing=frappe.db.exists("Communication Event",{"event_id":event_id})
    if existing:
        return existing
    doc=frappe.new_doc("Communication Event")
    doc.event_id=event_id
    _set(doc,"source",data.get("provider") or channel)
    _set(doc,"event_type","Chat" if channel not in ("email","manual_phone","android_call") else ("Email" if channel=="email" else "Call"))
    _set(doc,"direction",direction)
    _set(doc,"phone",normalize_phone(data.get("phone")))
    _set(doc,"email",(data.get("email") or "").strip().lower())
    _set(doc,"content",data.get("content"))
    _set(doc,"event_datetime",now_datetime())
    _set(doc,"recording_file",data.get("recording_file"))
    _set(doc,"duration",data.get("duration"))
    _set(doc,"provider",data.get("provider"))
    _set(doc,"provider_message_id",data.get("provider_message_id"))
    _set(doc,"assigned_user",assigned_to)
    _set(doc,"conversation_status","Open")
    _set(doc,"unread",1 if direction=="Inbound" else 0)
    _set(doc,"attachments",safe_json_dumps(data.get("attachments") or []))
    _set(doc,"raw_channel_payload",safe_json_dumps(data.get("raw_payload") or payload or {}))
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name

@frappe.whitelist()
def receive_channel(channel,payload=None):
    payload=load_json(payload,{}) if isinstance(payload,str) else (payload or frappe.form_dict)
    return {"event":record_interaction(channel,payload,"Inbound")}

def send_message(channel,to,content,customer=None,lead=None,visa_application=None,assigned_to=None,**kwargs):
    provider=get_provider(channel)
    result=provider.send(to,content,**kwargs)
    payload={"id":result.get("messages",[{}])[0].get("id") if isinstance(result,dict) else None,"phone":to,"email":to if "@" in str(to) else None,"content":content}
    name=record_interaction(channel,payload,"Outbound",assigned_to)
    values={k:v for k,v in {"customer":customer,"lead":lead,"visa_application":visa_application}.items() if v and has_field("Communication Event",k)}
    if values:
        frappe.db.set_value("Communication Event",name,values,update_modified=False)
    return {"event":name,"provider_result":result}

@frappe.whitelist()
def send_reply(channel,to,content,customer=None,lead=None,visa_application=None):
    return send_message(channel,to,content,customer=customer,lead=lead,visa_application=visa_application,assigned_to=frappe.session.user)

@frappe.whitelist()
def shared_inbox(filters=None,limit=50):
    if not has_doctype("Communication Event"):
        return {"rows":[],"counters":inbox_counters()}
    filters=load_json(filters,{}) if isinstance(filters,str) else (filters or {})
    query={}
    if filters.get("channel"):
        query["source"]=filters["channel"]
    if filters.get("status") and has_field("Communication Event","conversation_status"):
        query["conversation_status"]=filters["status"]
    if filters.get("assigned_to") and has_field("Communication Event","assigned_user"):
        query["assigned_user"]=filters["assigned_to"]
    if filters.get("label") and has_field("Communication Event","label"):
        query["label"]=filters["label"]
    fields=[f for f in ("name","event_id","source","event_type","direction","customer","lead","employee","phone","email","content","summary","sentiment","lead_score","event_datetime") if f=="name" or has_field("Communication Event",f)]
    fields += [f for f in ("unread","assigned_user","conversation_status","label","provider","provider_message_id","visa_application","ai_next_best_action","ai_customer_priority") if has_field("Communication Event",f)]
    order_by="event_datetime desc, modified desc" if has_field("Communication Event","event_datetime") else "modified desc"
    rows=frappe.get_all("Communication Event",filters=query,fields=fields or ["name"],order_by=order_by,limit_page_length=int(limit or 50))
    if filters.get("search"):
        term=str(filters.get("search")).lower()
        rows=[r for r in rows if term in " ".join([str(v or "") for v in r.values()]).lower()]
    return {"rows":rows,"counters":inbox_counters()}

@frappe.whitelist()
def get_inbox(filters=None,limit=50):
    return shared_inbox(filters,limit)

@frappe.whitelist()
def get_shared_inbox(filters=None,limit=50):
    return shared_inbox(filters,limit)

@frappe.whitelist()
def conversation(name):
    doc=frappe.get_doc("Communication Event",name)
    conditions=[]
    if getattr(doc,"phone",None):
        conditions.append(["phone","=",doc.phone])
    if getattr(doc,"email",None):
        conditions.append(["email","=",doc.email])
    if getattr(doc,"customer",None):
        conditions.append(["customer","=",doc.customer])
    fields=[f for f in ("name","source","direction","content","summary","event_datetime","customer","lead","phone","email") if f=="name" or has_field("Communication Event",f)]
    order_by="event_datetime asc" if has_field("Communication Event","event_datetime") else "modified asc"
    rows=frappe.get_all("Communication Event",or_filters=conditions,fields=fields,order_by=order_by) if conditions else [doc.as_dict()]
    return {"event":doc.as_dict(),"history":rows}

@frappe.whitelist()
def update_conversation(name,status=None,assigned_to=None,label=None,internal_note=None,mark_read=0):
    values={}
    if status:
        values["conversation_status"]=status
    if assigned_to:
        values["assigned_user"]=assigned_to
    if label:
        values["label"]=label
    if internal_note:
        values["internal_notes"]=internal_note
    if int(mark_read or 0):
        values["unread"]=0
    values={k:v for k,v in values.items() if has_field("Communication Event",k)}
    if values:
        frappe.db.set_value("Communication Event",name,values)
    return {"ok":True,"values":values}

@frappe.whitelist()
def quick_replies():
    return ["Thanks, we are checking this for you.","Please upload the pending documents.","Your counselor will contact you shortly.","Your visa application has been updated."]

@frappe.whitelist()
def templates(channel=None):
    return [{"name":"Document Request","content":"Please upload your pending visa documents."},{"name":"Payment Reminder","content":"Your next payment is pending. Please contact your counselor."},{"name":"Application Update","content":"Your visa application status has been updated."}]

def inbox_counters():
    out={"unread":0,"open":0,"pending":0}
    if has_field("Communication Event","unread"):
        out["unread"]=frappe.db.count("Communication Event",{"unread":1})
    if has_field("Communication Event","conversation_status"):
        out["open"]=frappe.db.count("Communication Event",{"conversation_status":"Open"})
        out["pending"]=frappe.db.count("Communication Event",{"conversation_status":"Pending"})
    return out

def enqueue_ai(event_name):
    frappe.enqueue("visa_crm.api.ai_intelligence.process_communication_ai",queue="long",enqueue_after_commit=True,event_name=event_name)

def _latest_visa(lead=None,customer=None):
    if not has_doctype("Visa Application"):
        return None
    filters={}
    if lead and has_field("Visa Application","lead"):
        filters["lead"]=lead
    elif customer and has_field("Visa Application","customer"):
        filters["customer"]=customer
    return frappe.db.get_value("Visa Application",filters,"name",order_by="modified desc") if filters else None

def _set(doc,field,value):
    if value is not None:
        set_if_has(doc,field,value)
