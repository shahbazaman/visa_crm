import frappe
from frappe.utils import now_datetime,time_diff_in_seconds
from visa_crm.api.meta_utils import has_doctype,has_field

def execute(filters=None):
    columns=[
        {"fieldname":"metric","label":"Metric","fieldtype":"Data","width":220},
        {"fieldname":"status","label":"Status","fieldtype":"Data","width":110},
        {"fieldname":"value","label":"Value","fieldtype":"Data","width":160},
        {"fieldname":"details","label":"Details","fieldtype":"Data","width":420}
    ]
    return columns,_rows()

def _rows():
    rows=[]
    queue="Lead Intake Queue"
    stage="Lead Intake Stage"
    log="Pipeline Execution Log"
    rows.append(_row("Webhook health","Healthy" if _recent(queue,"creation",1440) else "Warning",_latest(queue,"creation"),"Latest webhook-backed queue intake"))
    graph_success=_count(queue,{"graph_payload":["is","set"]})
    rows.append(_row("Graph API health","Healthy" if graph_success else "Warning",graph_success,"Queues containing a Graph payload"))
    backlog=_count(stage,{"state":["in",["NOT_STARTED","RUNNING","FAILED"]]})
    rows.append(_row("Pipeline health","Healthy" if not _count(stage,{"state":"FAILED"}) else "Warning",_count(queue,{}),f"{backlog} incomplete stages"))
    rows.append(_row("Queue backlog","Healthy" if backlog<100 else "Warning",backlog,"Incomplete durable pipeline stages"))
    rows.append(_row("Retry queue","Warning" if _count(stage,{"state":"FAILED"}) else "Healthy",_count(stage,{"state":"FAILED"}),"Failed stages awaiting retry"))
    rows.append(_row("Scheduler execution history","Healthy" if _count(log,{"execution_type":"Scheduler"}) else "Warning",_latest(log,"execution_time"),"Latest durable scheduler execution"))
    ai_failed=_count("Lead Intake AI Job",{"state":"FAILED"})
    rows.append(_row("AI queue health","Warning" if ai_failed else "Healthy",ai_failed,"Failed AI jobs; business processing remains independent"))
    rows.append(_row("Failed stages","Warning" if _count(stage,{"state":"FAILED"}) else "Healthy",_count(stage,{"state":"FAILED"}),"Stage-specific failures"))
    avg=frappe.db.sql("select round(avg(duration_ms),0) from `tabPipeline Execution Log` where result='SUCCESS'")[0][0] if has_doctype(log) else 0
    rows.append(_row("Average processing duration","Healthy",f"{avg or 0} ms","Average successful execution duration"))
    assignment=_count(stage,{"stage":"COUNSELOR_ASSIGNMENT","state":"FAILED"})
    rows.append(_row("Assignment failures","Warning" if assignment else "Healthy",assignment,"Retryable counselor assignment stages"))
    gemini=_count("Lead Intake AI Job",{"state":"FAILED"})
    rows.append(_row("Gemini failures","Warning" if gemini else "Healthy",gemini,"Persistent AI failures"))
    android=_count("Call Intelligence",{"metadata_status":["in",["Waiting","Missing","Warning"]]}) if has_field("Call Intelligence","metadata_status") else 0
    rows.append(_row("Android metadata pairing","Warning" if android else "Healthy",android,"Recordings waiting for metadata or carrying validation warnings"))
    return rows

def _row(metric,status,value,details):
    return {"metric":metric,"status":status,"value":str(value or 0),"details":details}

def _count(doctype,filters):
    return frappe.db.count(doctype,filters) if has_doctype(doctype) else 0

def _latest(doctype,field):
    if not has_doctype(doctype) or not has_field(doctype,field):
        return None
    rows=frappe.get_all(doctype,fields=[field],order_by=f"{field} desc",limit=1)
    return rows[0].get(field) if rows else None

def _recent(doctype,field,minutes):
    value=_latest(doctype,field)
    return bool(value and time_diff_in_seconds(now_datetime(),value)<=minutes*60)
