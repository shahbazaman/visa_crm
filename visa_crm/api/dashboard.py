import frappe
from visa_crm.api.meta_utils import has_doctype, has_field

@frappe.whitelist()
def manager_kpis():
    _staff()
    data = crm_metrics()
    data.update({
        "customers": _safe_count("Customer"),
        "leads": _safe_count("CRM Lead"),
        "calls": _safe_count("Call Intelligence"),
        "communication_events": _safe_count("Communication Event"),
        "todos": _safe_count("ToDo", {"status": "Open"}),
        "hot_leads": _safe_count("Lead Score History", {"score": [">=", 80]}),
        "medium_leads": _safe_count("Lead Score History", {"score": ["between", [40, 79]]}),
        "cold_leads": _safe_count("Lead Score History", {"score": ["<", 40]})
    })
    return data

@frappe.whitelist()
def crm_metrics():
    _staff()
    return {
        "new_leads": _count_stage("New"),
        "active_leads": _count_active(),
        "pending_documents": _count_stage("Documents Pending"),
        "visa_processing": _count_stage("Visa Processing"),
        "approvals": _count_stage("Approved"),
        "rejections": _count_stage("Rejected"),
        "lost_leads": _count_stage("Lost"),
        "counselor_performance": _group_count("CRM Lead", "assigned_employee"),
        "source_performance": _group_count("CRM Lead", "source"),
        "followup_compliance": _followup_compliance()
    }

@frappe.whitelist()
def lead_kanban():
    _staff()
    return _group_count("CRM Lead", _stage_field())

def _count_stage(stage):
    field = _stage_field()
    return frappe.db.count("CRM Lead", {field: stage}) if field else 0

def _count_active():
    field = _stage_field()
    return frappe.db.count("CRM Lead", {field: ["not in", ["Approved", "Rejected", "Cancelled", "Lost"]]}) if field else frappe.db.count("CRM Lead")

def _group_count(doctype, field):
    if not field or not has_doctype(doctype) or not has_field(doctype,field):
        return []
    return frappe.db.sql(f"select `{field}` label,count(*) value from `tab{doctype}` where ifnull(`{field}`,'')!='' group by `{field}` order by value desc", as_dict=True)

def _followup_compliance():
    open_todos = _safe_count("ToDo", {"status": "Open"})
    overdue = _safe_count("ToDo", {"status": "Open", "date": ["<", frappe.utils.today()]})
    return {"open": open_todos, "overdue": overdue, "compliance": 100 if not open_todos else round((open_todos - overdue) * 100 / open_todos, 2)}

def _stage_field():
    if not has_doctype("CRM Lead"):
        return None
    meta = frappe.get_meta("CRM Lead")
    for field in ("workflow_stage", "workflow_state", "stage", "status"):
        if meta.has_field(field):
            return field
    return None

def _safe_count(doctype, filters=None):
    return frappe.db.count(doctype, filters or {}) if has_doctype(doctype) else 0

def _staff():
    if frappe.session.user=="Guest" or not ({"System Manager","Sales Manager","Counselor","Visa Processing","Administrator"} & set(frappe.get_roles())):
        frappe.throw("Visa CRM staff access required", frappe.PermissionError)
