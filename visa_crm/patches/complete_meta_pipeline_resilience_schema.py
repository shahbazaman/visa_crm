import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field
from visa_crm.api.meta_utils import has_doctype,has_field
from visa_crm.api.stage_definitions import PIPELINE_VERSION

FIELDS={
    "Communication Event":(
        {"fieldname":"lead_intake_queue","label":"Lead Intake Queue","fieldtype":"Link","options":"Lead Intake Queue","insert_after":"channel_id"},
        {"fieldname":"followup_reference","label":"Follow-up","fieldtype":"Link","options":"ToDo","insert_after":"lead_intake_queue"}
    ),
    "Lead Assignment":(
        {"fieldname":"lead_intake_queue","label":"Lead Intake Queue","fieldtype":"Link","options":"Lead Intake Queue","insert_after":"meta_intake_key"},
        {"fieldname":"communication_event","label":"Communication Event","fieldtype":"Link","options":"Communication Event","insert_after":"lead_intake_queue"}
    ),
    "Counselor Assignment History":(
        {"fieldname":"lead_intake_queue","label":"Lead Intake Queue","fieldtype":"Link","options":"Lead Intake Queue","insert_after":"meta_intake_key"},
        {"fieldname":"communication_event","label":"Communication Event","fieldtype":"Link","options":"Communication Event","insert_after":"lead_intake_queue"}
    ),
    "Lead Timeline":(
        {"fieldname":"meta_intake_key","label":"Meta Intake Key","fieldtype":"Data","insert_after":"lead"},
    )
}

def execute():
    _fields()
    _indexes()
    _backfill_communication_links()
    _backfill_assignment_links()
    _backfill_ai_jobs()
    frappe.clear_cache()
    frappe.db.commit()

def _fields():
    for doctype,fields in FIELDS.items():
        if not has_doctype(doctype):
            continue
        for field in fields:
            if not has_field(doctype,field["fieldname"]):
                create_custom_field(doctype,dict(field))
        frappe.clear_cache(doctype=doctype)

def _indexes():
    for doctype,fields,name in (
        ("Lead Intake AI Job",["state","next_retry_at"],"idx_vc_ai_job_due"),
        ("Lead Intake AI Job",["queue","state"],"idx_vc_ai_job_queue"),
        ("Communication Event",["lead_intake_queue"],"idx_vc_comm_queue")
    ):
        _safe_index(doctype,fields,name)
    _safe_unique("Lead Timeline","meta_intake_key","uniq_vc_lead_timeline_intake")

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

def _backfill_communication_links():
    if not has_doctype("Lead Intake Queue") or not has_doctype("Communication Event"):
        return
    fields=["name"]+[field for field in ("communication_event","followup_reference") if has_field("Lead Intake Queue",field)]
    for queue in frappe.get_all("Lead Intake Queue",filters={"communication_event":["is","set"]},fields=fields,limit_page_length=0):
        if not queue.communication_event or not frappe.db.exists("Communication Event",queue.communication_event):
            continue
        current=frappe.db.get_value("Communication Event",queue.communication_event,["lead_intake_queue","followup_reference"],as_dict=True) or {}
        values={}
        if not current.get("lead_intake_queue"):
            values["lead_intake_queue"]=queue.name
        if queue.get("followup_reference") and not current.get("followup_reference"):
            values["followup_reference"]=queue.followup_reference
        if values:
            frappe.db.set_value("Communication Event",queue.communication_event,values,update_modified=False)

def _backfill_assignment_links():
    if not has_doctype("Lead Intake Queue"):
        return
    for doctype in ("Lead Assignment","Counselor Assignment History"):
        if not has_doctype(doctype) or not has_field(doctype,"meta_intake_key"):
            continue
        rows=frappe.get_all(doctype,filters={"meta_intake_key":["like","assignment%:%"]},fields=["name","meta_intake_key"],limit_page_length=0)
        for row in rows:
            queue_name=row.meta_intake_key.split(":",1)[1]
            if not frappe.db.exists("Lead Intake Queue",queue_name):
                continue
            values={"lead_intake_queue":queue_name}
            event=frappe.db.get_value("Lead Intake Queue",queue_name,"communication_event")
            if event:
                values["communication_event"]=event
            missing={field:value for field,value in values.items() if has_field(doctype,field) and not frappe.db.get_value(doctype,row.name,field)}
            if missing:
                frappe.db.set_value(doctype,row.name,missing,update_modified=False)

def _backfill_ai_jobs():
    if not has_doctype("Lead Intake AI Job") or not has_doctype("Lead Intake Queue"):
        return
    fields=["name"]+[field for field in ("communication_event","ai_status","ai_error","ai_traceback","ai_retry_count") if has_field("Lead Intake Queue",field)]
    for queue in frappe.get_all("Lead Intake Queue",filters={"communication_event":["is","set"]},fields=fields,limit_page_length=0):
        if not queue.communication_event or not frappe.db.exists("Communication Event",queue.communication_event):
            continue
        key=f"ai:{queue.communication_event}:{PIPELINE_VERSION}"
        if frappe.db.exists("Lead Intake AI Job",key):
            continue
        state={"Completed":"COMPLETED","Queued":"QUEUED","Running":"RUNNING","Failed":"FAILED"}.get(queue.get("ai_status"),"PENDING")
        doc=frappe.new_doc("Lead Intake AI Job")
        doc.update({"idempotency_key":key,"queue":queue.name,"communication_event":queue.communication_event,"pipeline_version":PIPELINE_VERSION,"state":state,"attempt_count":queue.get("ai_retry_count") or 0,"last_error":queue.get("ai_error"),"last_traceback":queue.get("ai_traceback")})
        doc.insert(ignore_permissions=True,ignore_if_duplicate=True)
