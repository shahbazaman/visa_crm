import hashlib
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field
from visa_crm.api.meta_utils import has_doctype,has_field,safe_json_dumps
from visa_crm.api.stage_definitions import PIPELINE_VERSION,STAGES

QUEUE_FIELDS=(
    {"fieldname":"orchestration_status","label":"Orchestration Status","fieldtype":"Select","options":"PENDING\nRUNNING\nCOMPLETED\nCOMPLETED_WITH_WARNINGS\nPARTIALLY_COMPLETED\nFAILED\nIGNORED","default":"PENDING","insert_after":"status"},
    {"fieldname":"pipeline_version","label":"Pipeline Version","fieldtype":"Int","default":str(PIPELINE_VERSION),"insert_after":"orchestration_status"},
    {"fieldname":"current_stage","label":"Current Stage","fieldtype":"Data","insert_after":"pipeline_version"},
    {"fieldname":"last_progress_at","label":"Last Progress At","fieldtype":"Datetime","insert_after":"current_stage"},
    {"fieldname":"next_action_at","label":"Next Action At","fieldtype":"Datetime","insert_after":"last_progress_at"},
    {"fieldname":"warning_count","label":"Warning Count","fieldtype":"Int","default":"0","insert_after":"next_action_at"},
    {"fieldname":"stage_summary_json","label":"Stage Summary","fieldtype":"Long Text","insert_after":"warning_count"},
    {"fieldname":"duplicate_of","label":"Canonical Queue","fieldtype":"Link","options":"Lead Intake Queue","insert_after":"stage_summary_json"},
    {"fieldname":"normalization_version","label":"Normalization Version","fieldtype":"Data","insert_after":"custom_answers"},
    {"fieldname":"normalized_payload","label":"Normalized Payload","fieldtype":"Long Text","insert_after":"normalization_version"},
    {"fieldname":"normalized_payload_hash","label":"Normalized Payload Hash","fieldtype":"Data","insert_after":"normalized_payload"},
    {"fieldname":"graph_payload_hash","label":"Graph Payload Hash","fieldtype":"Data","insert_after":"graph_payload"}
)
LEAD_FIELDS=(
    ("facebook_lead_id","Facebook Lead ID"),("facebook_form_id","Facebook Form ID"),("facebook_page_id","Facebook Page ID"),
    ("meta_campaign_id","Meta Campaign ID"),("meta_campaign_name","Meta Campaign Name"),("meta_adset_id","Meta Adset ID"),
    ("meta_adset_name","Meta Adset Name"),("meta_ad_id","Meta Ad ID"),("meta_ad_name","Meta Ad Name")
)
IDEMPOTENCY_DOCTYPES=("Visa Application","ToDo","Reminder Scheduler","Activity Timeline","Lead Assignment","Counselor Assignment History")

def execute():
    _custom_fields()
    _queue_status_options()
    _indexes()
    _backfill_attribution()
    _backfill_stages()
    frappe.clear_cache()
    frappe.db.commit()

def _custom_fields():
    _ensure_fields("Lead Intake Queue",QUEUE_FIELDS)
    _ensure_fields("CRM Lead",tuple({"fieldname":field,"label":label,"fieldtype":"Data","insert_after":"facebook_lead_id"} for field,label in LEAD_FIELDS))
    for doctype in IDEMPOTENCY_DOCTYPES:
        if not has_doctype(doctype):
            continue
        _ensure_fields(doctype,({"fieldname":"meta_intake_key","label":"Meta Intake Key","fieldtype":"Data","insert_after":_insert_after(doctype)},))

def _ensure_fields(doctype,fields):
    if not has_doctype(doctype):
        return
    for field in fields:
        if has_field(doctype,field["fieldname"]):
            continue
        create_custom_field(doctype,dict(field))
    frappe.clear_cache(doctype=doctype)

def _insert_after(doctype):
    meta=frappe.get_meta(doctype)
    for field in ("reference_name","lead","customer","status"):
        if meta.has_field(field):
            return field
    return None

def _queue_status_options():
    if not has_doctype("Lead Intake Queue"):
        return
    name=frappe.db.get_value("DocField",{"parent":"Lead Intake Queue","fieldname":"status"},"name")
    if not name:
        return
    current=frappe.db.get_value("DocField",name,"options") or ""
    options=[row for row in current.splitlines() if row]
    for value in ("Processed With Warnings","Needs Retry","Action Required"):
        if value not in options:
            options.append(value)
    frappe.db.set_value("DocField",name,"options","\n".join(options),update_modified=False)

def _indexes():
    for doctype,fields,name in (
        ("Lead Intake Stage",["state","next_retry_at","sequence"],"idx_vc_stage_due"),
        ("Lead Intake Stage",["lease_expires_at","state"],"idx_vc_stage_lease"),
        ("Lead Intake Stage",["queue","sequence"],"idx_vc_stage_queue"),
        ("Customer Identity",["customer","identity_type"],"idx_vc_identity_customer"),
        ("Lead Intake Queue",["orchestration_status","next_action_at"],"idx_vc_queue_orchestration")
    ):
        _safe_index(doctype,fields,name)
    for doctype,field,name in (
        ("CRM Lead","facebook_lead_id","uniq_vc_facebook_lead"),
        ("Communication Event","event_id","uniq_vc_communication_event"),
        ("Visa Application","meta_intake_key","uniq_vc_visa_intake"),
        ("ToDo","meta_intake_key","uniq_vc_todo_intake"),
        ("Reminder Scheduler","meta_intake_key","uniq_vc_reminder_intake"),
        ("Activity Timeline","meta_intake_key","uniq_vc_activity_intake"),
        ("Lead Assignment","meta_intake_key","uniq_vc_assignment_intake"),
        ("Counselor Assignment History","meta_intake_key","uniq_vc_assignment_history_intake")
    ):
        _safe_unique(doctype,field,name)

def _safe_index(doctype,fields,name):
    if not has_doctype(doctype) or not all(has_field(doctype,field) for field in fields) or _index_exists(doctype,name):
        return
    frappe.db.add_index(doctype,fields,index_name=name)

def _safe_unique(doctype,field,name):
    if not has_doctype(doctype) or not has_field(doctype,field) or _unique_field_exists(doctype,field):
        return
    duplicates=frappe.db.sql(f"""select `{field}`,count(*) total from `tab{doctype}` where ifnull(`{field}`,'')!='' group by `{field}` having count(*)>1 limit 1""",as_dict=True)
    if duplicates:
        frappe.logger("visa_crm.migration").warning({"event":"unique_index_skipped","doctype":doctype,"field":field,"value":duplicates[0].get(field),"count":duplicates[0].total})
        return
    frappe.db.sql(f"""update `tab{doctype}` set `{field}`=null where `{field}`=''""")
    frappe.db.add_unique(doctype,[field],constraint_name=name)

def _index_exists(doctype,name):
    return any(row.Key_name==name for row in frappe.db.sql(f"show index from `tab{doctype}`",as_dict=True))

def _unique_field_exists(doctype,field):
    return any(row.Column_name==field and not row.Non_unique for row in frappe.db.sql(f"show index from `tab{doctype}`",as_dict=True))

def _backfill_attribution():
    if not has_doctype("Lead Intake Queue") or not has_doctype("CRM Lead"):
        return
    fields=["name"]+[field for field in ("matched_lead","source_lead_id","form_id","page_id","campaign_id","campaign_name","adset_id","adset_name","ad_id","ad_name") if has_field("Lead Intake Queue",field)]
    rows=frappe.get_all("Lead Intake Queue",filters={"matched_lead":["is","set"]},fields=fields,limit_page_length=0)
    mapping={"source_lead_id":"facebook_lead_id","form_id":"facebook_form_id","page_id":"facebook_page_id","campaign_id":"meta_campaign_id","campaign_name":"meta_campaign_name","adset_id":"meta_adset_id","adset_name":"meta_adset_name","ad_id":"meta_ad_id","ad_name":"meta_ad_name"}
    for row in rows:
        if not frappe.db.exists("CRM Lead",row.matched_lead):
            continue
        current=frappe.db.get_value("CRM Lead",row.matched_lead,list(mapping.values()),as_dict=True) or {}
        values={target:row.get(source) for source,target in mapping.items() if row.get(source) and not current.get(target)}
        if values:
            frappe.db.set_value("CRM Lead",row.matched_lead,values,update_modified=False)

def _backfill_stages():
    if not has_doctype("Lead Intake Queue") or not has_doctype("Lead Intake Stage"):
        return
    fields=["name","modified"]+[field for field in ("status","source_lead_id","raw_payload","graph_payload","graph_api_response","custom_answers","customer_name","phone","email","matched_customer","matched_lead","visa_application","communication_event","followup_reference","assigned_employee","ai_status","ai_error") if has_field("Lead Intake Queue",field)]
    for queue in frappe.get_all("Lead Intake Queue",fields=fields,limit_page_length=0):
        for definition in STAGES:
            _ensure_stage(queue,definition)
        _backfill_queue_summary(queue)

def _ensure_stage(queue,definition):
    key=f"{queue.name}:{definition['stage']}"
    if frappe.db.exists("Lead Intake Stage",key):
        return
    state,result_doctype,result_name,warning,error=_evidence(queue,definition["stage"])
    doc=frappe.new_doc("Lead Intake Stage")
    doc.update({"stage_key":key,"queue":queue.name,"stage":definition["stage"],"sequence":definition["sequence"],"parent_stage":definition.get("parent_stage"),"requirement_class":definition["requirement_class"],"state":state,"attempt_count":0,"max_attempts":definition["max_attempts"],"result_doctype":result_doctype,"result_name":result_name,"warning":warning,"last_error":error})
    if state=="COMPLETED":
        doc.completed_at=queue.modified
    doc.insert(ignore_permissions=True,ignore_if_duplicate=True)

def _evidence(queue,stage):
    processed=queue.get("status") in ("Processed","Completed","Processed With Warnings")
    if stage=="WEBHOOK":
        return "COMPLETED","Lead Intake Queue",queue.name,0,None
    if stage=="GRAPH_DOWNLOAD" and (queue.get("graph_payload") or queue.get("graph_api_response")):
        return "COMPLETED",None,None,0,None
    if stage=="NORMALIZE" and (queue.get("custom_answers") or queue.get("customer_name") or queue.get("phone") or queue.get("email")):
        return "COMPLETED",None,None,0,None
    links={"CUSTOMER360":("Customer","matched_customer"),"CRM_LEAD":("CRM Lead","matched_lead"),"VISA_APPLICATION":("Visa Application","visa_application"),"COMMUNICATION_EVENT":("Communication Event","communication_event"),"FOLLOW_UP":("ToDo","followup_reference")}
    if stage in links:
        doctype,field=links[stage]
        value=queue.get(field)
        return ("COMPLETED",doctype,value,0,None) if value and frappe.db.exists(doctype,value) else ("NOT_STARTED",None,None,0,None)
    if stage=="LEAD_WORKFLOW" and processed and queue.get("matched_lead"):
        return "COMPLETED","CRM Lead",queue.matched_lead,0,None
    if stage=="COUNSELOR_ASSIGNMENT":
        if queue.get("assigned_employee"):
            return "COMPLETED","Employee",queue.assigned_employee,0,None
        if processed:
            return "FAILED",None,None,1,"No assignment recorded during legacy processing"
    if stage=="AI_DISPATCH":
        status=queue.get("ai_status")
        if status in ("Queued","Completed"):
            return "COMPLETED",None,None,0,None
        if status=="Failed":
            return "FAILED",None,None,1,queue.get("ai_error")
    if stage.startswith("AI_") and processed:
        return "NOT_STARTED",None,None,0,None
    return "NOT_STARTED",None,None,0,None

def _backfill_queue_summary(queue):
    from visa_crm.api.pipeline_engine import rollup_queue
    rollup_queue(queue.name)
