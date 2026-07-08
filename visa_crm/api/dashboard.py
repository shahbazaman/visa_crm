import frappe

@frappe.whitelist()
def manager_kpis():
    data = crm_metrics()
    data.update({
        "customers": frappe.db.count("Customer"),
        "leads": frappe.db.count("CRM Lead"),
        "calls": frappe.db.count("Call Intelligence"),
        "communication_events": frappe.db.count("Communication Event"),
        "todos": frappe.db.count("ToDo", {"status": "Open"}),
        "hot_leads": frappe.db.count("Lead Score History", {"score": [">=", 80]}),
        "medium_leads": frappe.db.count("Lead Score History", {"score": ["between", [40, 79]]}),
        "cold_leads": frappe.db.count("Lead Score History", {"score": ["<", 40]})
    })
    return data

@frappe.whitelist()
def crm_metrics():
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
    return _group_count("CRM Lead", _stage_field())

def _count_stage(stage):
    field = _stage_field()
    return frappe.db.count("CRM Lead", {field: stage}) if field else 0

def _count_active():
    field = _stage_field()
    return frappe.db.count("CRM Lead", {field: ["not in", ["Approved", "Rejected", "Cancelled", "Lost"]]}) if field else frappe.db.count("CRM Lead")

def _group_count(doctype, field):
    if not field or not frappe.get_meta(doctype).has_field(field):
        return []
    return frappe.db.sql(f"select `{field}` label,count(*) value from `tab{doctype}` where ifnull(`{field}`,'')!='' group by `{field}` order by value desc", as_dict=True)

def _followup_compliance():
    open_todos = frappe.db.count("ToDo", {"status": "Open"})
    overdue = frappe.db.count("ToDo", {"status": "Open", "date": ["<", frappe.utils.today()]})
    return {"open": open_todos, "overdue": overdue, "compliance": 100 if not open_todos else round((open_todos - overdue) * 100 / open_todos, 2)}

def _stage_field():
    meta = frappe.get_meta("CRM Lead")
    for field in ("workflow_stage", "workflow_state", "stage", "status"):
        if meta.has_field(field):
            return field
    return None
