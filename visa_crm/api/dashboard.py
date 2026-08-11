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

@frappe.whitelist()
def employee_performance_dashboard(
    employee=None,
    from_date=None,
    to_date=None,
    lead_source=None,
    category=None,
    subcategory=None,
    visa_type=None,
    country=None,
    lead_status=None,
):
    from visa_crm.api.lead_permissions import is_management, is_operational

    if frappe.session.user == "Guest" or not is_operational():
        frappe.throw("Visa CRM operational access required", frappe.PermissionError)

    user_emp = frappe.db.get_value("Employee", {"user_id": frappe.session.user, "status": "Active"}, "name")
    if not is_management():
        if employee and employee != user_emp:
            frappe.throw("Not authorized to view performance data for other employees", frappe.PermissionError)
        employee = user_emp or employee

    filters = {}
    if employee:
        filters["assigned_employee"] = employee
    if lead_source:
        filters["source"] = lead_source
    if category and category != "All":
        filters["lead_category"] = category
    if subcategory and subcategory not in ("All", "Unspecified", "No Subcategory"):
        filters["lead_group"] = subcategory
    if visa_type:
        filters["visa_type"] = visa_type
    if country:
        filters["country_interested"] = country
    if lead_status:
        filters["status"] = lead_status
    if from_date:
        filters["creation"] = [">=", frappe.utils.getdate(from_date)]
    if to_date:
        if "creation" in filters:
            filters["creation"] = ["between", [frappe.utils.getdate(from_date), frappe.utils.getdate(to_date)]]
        else:
            filters["creation"] = ["<=", frappe.utils.getdate(to_date)]

    leads_data = frappe.get_all(
        "CRM Lead",
        filters=filters,
        fields=["name", "status", "source", "lead_category", "lead_group", "visa_type", "country_interested", "assigned_employee", "creation"],
        order_by="creation desc",
        page_length=0,
    )

    total_leads = len(leads_data)
    new_leads = sum(1 for l in leads_data if str(l.status or "").lower() in ("new", "lead", "open", ""))
    active_leads = sum(1 for l in leads_data if str(l.status or "").lower() not in ("approved", "rejected", "cancelled", "lost", "converted"))
    converted_leads = sum(1 for l in leads_data if str(l.status or "").lower() in ("approved", "converted", "won"))
    lost_leads = sum(1 for l in leads_data if str(l.status or "").lower() == "lost")
    pending_leads = sum(1 for l in leads_data if "pending" in str(l.status or "").lower())

    conversion_rate = round((converted_leads * 100.0 / total_leads), 1) if total_leads else 0.0

    deals_count = 0
    if total_leads and has_doctype("CRM Deal"):
        lead_names = [l.name for l in leads_data]
        deals_count = frappe.db.count("CRM Deal", {"lead": ["in", lead_names]}) if lead_names else 0

    visas_count = 0
    completed_visas = 0
    if total_leads and has_doctype("Visa Application"):
        lead_names = [l.name for l in leads_data]
        visas_count = frappe.db.count("Visa Application", {"lead": ["in", lead_names]}) if lead_names else 0
        completed_visas = frappe.db.count("Visa Application", {"lead": ["in", lead_names], "status": "Completed"}) if lead_names else 0

    lead_to_deal_rate = round((deals_count * 100.0 / total_leads), 1) if total_leads else 0.0
    deal_to_visa_rate = round((visas_count * 100.0 / deals_count), 1) if deals_count else 0.0
    visa_completion_rate = round((completed_visas * 100.0 / visas_count), 1) if visas_count else 0.0

    comm_filters = {}
    if employee:
        comm_filters["employee"] = employee

    total_calls = 0
    total_chats = 0
    total_emails = 0
    answered_comms = 0
    missed_comms = 0

    if has_doctype("Communication Event"):
        comm_events = frappe.get_all("Communication Event", filters=comm_filters, fields=["communication_type", "status", "sentiment", "overall_score"])
        for c in comm_events:
            ctype = str(c.communication_type or "").lower()
            if "call" in ctype:
                total_calls += 1
            elif "chat" in ctype or "whatsapp" in ctype or "message" in ctype:
                total_chats += 1
            elif "email" in ctype:
                total_emails += 1
            st = str(c.status or "").lower()
            if "answered" in st or "completed" in st or "sent" in st:
                answered_comms += 1
            elif "missed" in st or "failed" in st:
                missed_comms += 1

    todo_filters = {"status": "Open"}
    if employee:
        todo_filters["allocated_to"] = frappe.db.get_value("Employee", employee, "user_id") or ""
    open_todos = _safe_count("ToDo", todo_filters)
    todo_filters_overdue = dict(todo_filters)
    todo_filters_overdue["date"] = ["<", frappe.utils.today()]
    overdue_todos = _safe_count("ToDo", todo_filters_overdue)
    followup_compliance = 100.0 if not open_todos else round((open_todos - overdue_todos) * 100.0 / open_todos, 1)

    eval_filters = {}
    if employee:
        eval_filters["employee"] = employee

    overall_ai_score = 0.0
    eval_count = 0
    friendliness = 0.0
    empathy = 0.0
    professionalism = 0.0
    clarity = 0.0
    responsiveness = 0.0
    policy_compliance = 0.0
    coaching_list = []

    if has_doctype("Employee Evaluation"):
        evals = frappe.get_all(
            "Employee Evaluation",
            filters=eval_filters,
            fields=["overall_score", "friendliness", "empathy", "professionalism", "clarity", "responsiveness", "policy_compliance", "coaching_tips", "ai_feedback"],
            order_by="creation desc",
            limit_page_length=50,
        )
        eval_count = len(evals)
        if eval_count:
            overall_ai_score = round(sum((e.overall_score or 0) for e in evals) / float(eval_count), 1)
            friendliness = round(sum((e.friendliness or 0) for e in evals) / float(eval_count), 1)
            empathy = round(sum((e.empathy or 0) for e in evals) / float(eval_count), 1)
            professionalism = round(sum((e.professionalism or 0) for e in evals) / float(eval_count), 1)
            clarity = round(sum((e.clarity or 0) for e in evals) / float(eval_count), 1)
            responsiveness = round(sum((e.responsiveness or 0) for e in evals) / float(eval_count), 1)
            policy_compliance = round(sum((e.policy_compliance or 0) for e in evals) / float(eval_count), 1)
            for e in evals:
                if e.coaching_tips:
                    coaching_list.append(e.coaching_tips)

    rankings = []
    if is_management():
        employees_list = frappe.get_all("Employee", filters={"status": "Active"}, fields=["name", "employee_name", "department", "designation"])
        for emp in employees_list:
            emp_leads = [l for l in leads_data if l.assigned_employee == emp.name] if not employee else (leads_data if employee == emp.name else [])
            emp_total = len(emp_leads)
            emp_converted = sum(1 for l in emp_leads if str(l.status or "").lower() in ("approved", "converted", "won"))
            emp_conv_rate = round((emp_converted * 100.0 / emp_total), 1) if emp_total else 0.0

            emp_evals = frappe.get_all("Employee Evaluation", filters={"employee": emp.name}, fields=["overall_score"])
            emp_eval_count = len(emp_evals)
            emp_score = round(sum((e.overall_score or 0) for e in emp_evals) / float(emp_eval_count), 1) if emp_eval_count else 0.0

            rankings.append({
                "employee": emp.name,
                "employee_name": emp.employee_name,
                "department": emp.department,
                "designation": emp.designation,
                "assigned_leads": emp_total,
                "converted_leads": emp_converted,
                "conversion_rate": emp_conv_rate,
                "ai_score": emp_score,
                "insufficient_data": emp_total < 3 or emp_eval_count < 2,
            })
        rankings.sort(key=lambda r: (r["conversion_rate"], r["ai_score"], r["converted_leads"]), reverse=True)
        for idx, r in enumerate(rankings, 1):
            r["rank"] = idx

    source_breakdown = {}
    category_breakdown = {}
    uncategorized_count = 0

    for l in leads_data:
        src = l.source or "Unspecified"
        source_breakdown[src] = source_breakdown.get(src, 0) + 1

        cat = l.lead_category or "Uncategorized"
        sub = l.lead_group or "Unspecified"
        if cat == "Uncategorized" or not l.lead_category:
            uncategorized_count += 1

        if cat not in category_breakdown:
            category_breakdown[cat] = {"total": 0, "subcategories": {}}
        category_breakdown[cat]["total"] += 1
        category_breakdown[cat]["subcategories"][sub] = category_breakdown[cat]["subcategories"].get(sub, 0) + 1

    pipeline_health = {}
    if has_doctype("Lead Intake Queue"):
        pipeline_health = {
            "total_queues": _safe_count("Lead Intake Queue"),
            "action_required": _safe_count("Lead Intake Queue", {"status": "Action Required"}),
            "needs_retry": _safe_count("Lead Intake Queue", {"status": "Needs Retry"}),
            "processed": _safe_count("Lead Intake Queue", {"status": "Processed"}),
            "uncategorized_leads": uncategorized_count,
        }
        if has_doctype("Lead Intake Stage"):
            pipeline_health["failed_stages"] = _safe_count("Lead Intake Stage", {"state": "FAILED"})
            pipeline_health["blocked_stages"] = _safe_count("Lead Intake Stage", {"state": "BLOCKED"})
        if has_doctype("Lead Intake AI Job"):
            pipeline_health["ai_queued"] = _safe_count("Lead Intake AI Job", {"state": "QUEUED"})
            pipeline_health["ai_completed"] = _safe_count("Lead Intake AI Job", {"state": "COMPLETED"})
            pipeline_health["ai_failed"] = _safe_count("Lead Intake AI Job", {"state": "FAILED"})

    emp_details = None
    if employee:
        emp_doc = frappe.get_doc("Employee", employee)
        emp_details = {
            "name": emp_doc.name,
            "employee_name": emp_doc.employee_name,
            "department": emp_doc.department,
            "designation": emp_doc.designation,
            "status": emp_doc.status,
            "user_id": emp_doc.user_id,
        }

    return {
        "employee_info": emp_details,
        "top_cards": {
            "total_leads": total_leads,
            "new_leads": new_leads,
            "active_leads": active_leads,
            "converted_leads": converted_leads,
            "lost_leads": lost_leads,
            "pending_leads": pending_leads,
            "conversion_rate": conversion_rate,
            "lead_to_deal_rate": lead_to_deal_rate,
            "deal_to_visa_rate": deal_to_visa_rate,
            "visa_completion_rate": visa_completion_rate,
        },
        "communication_performance": {
            "total_calls": total_calls,
            "total_chats": total_chats,
            "total_emails": total_emails,
            "answered_communications": answered_comms,
            "missed_communications": missed_comms,
            "open_todos": open_todos,
            "overdue_todos": overdue_todos,
            "followup_compliance": followup_compliance,
        },
        "ai_performance": {
            "overall_score": overall_ai_score,
            "evaluations_count": eval_count,
            "friendliness": friendliness,
            "empathy": empathy,
            "professionalism": professionalism,
            "clarity": clarity,
            "responsiveness": responsiveness,
            "policy_compliance": policy_compliance,
            "coaching_tips": coaching_list[:5],
            "insufficient_data": eval_count < 2,
        },
        "rankings": rankings,
        "source_breakdown": source_breakdown,
        "category_breakdown": category_breakdown,
        "uncategorized_count": uncategorized_count,
        "pipeline_health": pipeline_health,
        "generated_at": frappe.utils.now_datetime(),
    }
