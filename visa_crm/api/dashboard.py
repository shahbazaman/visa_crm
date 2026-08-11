import frappe
from frappe.utils import cint
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
def employee_list_for_dashboard():
    from visa_crm.api.lead_permissions import require_management
    require_management()
    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name", "department", "designation", "user_id", "status"],
        order_by="employee_name asc",
        page_length=0,
    )
    return employees


@frappe.whitelist()
def employee_performance_dashboard(
    employee=None,
    preset="this_month",
    from_date=None,
    to_date=None,
    lead_source=None,
    category=None,
    subcategory=None,
    visa_type=None,
    country=None,
    lead_status=None,
    channel=None,
    ai_status=None,
):
    from visa_crm.api.lead_permissions import require_management
    require_management()

    if not employee:
        emp_list = employee_list_for_dashboard()
        if emp_list:
            employee = emp_list[0].name
        else:
            frappe.throw("No active employees found in the system")

    start_date, end_date = _resolve_date_range(preset, from_date, to_date)

    emp_doc = frappe.get_doc("Employee", employee)
    emp_user_id = emp_doc.user_id

    lead_filters = {}
    if employee:
        lead_filters["assigned_employee"] = employee
    if lead_source:
        lead_filters["source"] = lead_source
    if category and category != "All":
        lead_filters["lead_category"] = category
    if subcategory and subcategory not in ("All", "Unspecified", "No Subcategory"):
        lead_filters["lead_group"] = subcategory
    if visa_type:
        lead_filters["visa_type"] = visa_type
    if country:
        lead_filters["country_interested"] = country
    if lead_status:
        lead_filters["status"] = lead_status
    if start_date and end_date:
        lead_filters["creation"] = ["between", [start_date, end_date]]

    leads_data = frappe.get_all(
        "CRM Lead",
        filters=lead_filters,
        fields=["name", "status", "source", "lead_category", "lead_group", "visa_type", "country_interested", "assigned_employee", "creation"],
        order_by="creation desc",
        page_length=0,
    )
    lead_names = [l.name for l in leads_data]

    comm_filters = {"employee": employee}
    if start_date and end_date:
        comm_filters["creation"] = ["between", [f"{start_date} 00:00:00", f"{end_date} 23:59:59"]]

    if channel:
        comm_filters["source"] = channel

    all_comm_events = frappe.get_all(
        "Communication Event",
        filters=comm_filters,
        fields=[
            "name", "creation", "event_datetime", "source", "event_type", "direction",
            "customer", "lead", "employee", "status", "sentiment", "lead_score", "ai_score",
            "duration", "response_time", "coaching_suggestion", "summary"
        ],
        order_by="creation desc",
        page_length=0,
    )

    channel_counts = {"Call": 0, "WhatsApp": 0, "Email": 0, "Instagram": 0, "Facebook": 0, "Other": 0}
    for c in all_comm_events:
        src = str(c.source or c.event_type or "").lower()
        if "call" in src or "phone" in src:
            channel_counts["Call"] += 1
        elif "whatsapp" in src:
            channel_counts["WhatsApp"] += 1
        elif "email" in src:
            channel_counts["Email"] += 1
        elif "instagram" in src:
            channel_counts["Instagram"] += 1
        elif "facebook" in src or "messenger" in src:
            channel_counts["Facebook"] += 1
        else:
            channel_counts["Other"] += 1

    total_interactions = len(all_comm_events)
    unique_customers = len(set(filter(None, [c.customer for c in all_comm_events])))
    unique_leads = len(set(filter(None, [c.lead for c in all_comm_events] + lead_names)))

    eval_filters = {"employee": employee}
    if start_date and end_date:
        eval_filters["creation"] = ["between", [f"{start_date} 00:00:00", f"{end_date} 23:59:59"]]

    evaluations = frappe.get_all(
        "Employee Evaluation",
        filters=eval_filters,
        fields=[
            "name", "communication_event", "overall_score", "friendliness", "professionalism",
            "empathy", "clarity", "responsiveness", "policy_compliance", "ai_feedback", "coaching_tips", "creation"
        ],
        order_by="creation desc",
        page_length=0,
    )

    eval_event_names = set(filter(None, [e.communication_event for e in evaluations]))
    ai_job_map = {}
    if has_doctype("Lead Intake AI Job") and all_comm_events:
        event_names = [c.name for c in all_comm_events]
        j_rows = frappe.get_all("Lead Intake AI Job", filters={"communication_event": ["in", event_names]}, fields=["communication_event", "state", "last_error"])
        ai_job_map = {j.communication_event: j for j in j_rows}

    ai_evaluated = 0
    ai_pending = 0
    ai_failed = 0
    ai_unavailable = 0

    evaluated_scores = []
    for c in all_comm_events:
        j_st = str(ai_job_map.get(c.name, frappe._dict()).get("state") or "").upper()
        matching_eval = next((e for e in evaluations if e.communication_event == c.name), None) if c.name in eval_event_names else None
        score = matching_eval.overall_score if (matching_eval and matching_eval.overall_score is not None) else (c.ai_score if (c.ai_score is not None and c.ai_score > 0) else None)

        if score is not None:
            ai_evaluated += 1
            evaluated_scores.append(score)
        elif j_st in ("FAILED", "ERROR") or str(c.status or "").lower() in ("failed", "error"):
            ai_failed += 1
        elif j_st in ("RUNNING", "QUEUED", "PENDING") or str(c.status or "").lower() in ("pending", "running"):
            ai_pending += 1
        else:
            ai_unavailable += 1

    if not evaluated_scores and evaluations:
        evaluated_scores = [e.overall_score for e in evaluations if e.overall_score is not None]
        ai_evaluated = len(evaluated_scores)

    avg_ai_score = round(sum(evaluated_scores) / float(len(evaluated_scores)), 1) if evaluated_scores else None
    insufficient_data = len(evaluated_scores) == 0

    friendliness = round(sum(e.friendliness or 0 for e in evaluations) / float(len(evaluations)), 1) if evaluations else 0.0
    empathy = round(sum(e.empathy or 0 for e in evaluations) / float(len(evaluations)), 1) if evaluations else 0.0
    professionalism = round(sum(e.professionalism or 0 for e in evaluations) / float(len(evaluations)), 1) if evaluations else 0.0
    clarity = round(sum(e.clarity or 0 for e in evaluations) / float(len(evaluations)), 1) if evaluations else 0.0
    responsiveness = round(sum(e.responsiveness or 0 for e in evaluations) / float(len(evaluations)), 1) if evaluations else 0.0
    policy_compliance = round(sum(e.policy_compliance or 0 for e in evaluations) / float(len(evaluations)), 1) if evaluations else 0.0

    todo_filters = {}
    if emp_user_id:
        todo_filters["allocated_to"] = emp_user_id
    if start_date and end_date:
        todo_filters["creation"] = ["between", [f"{start_date} 00:00:00", f"{end_date} 23:59:59"]]

    all_todos = frappe.get_all("ToDo", filters=todo_filters, fields=["status", "date"], page_length=0)
    total_todos = len(all_todos)
    completed_todos = sum(1 for t in all_todos if str(t.status or "").lower() in ("closed", "completed"))
    overdue_todos = sum(1 for t in all_todos if str(t.status or "").lower() == "open" and t.date and str(t.date) < str(frappe.utils.today()))
    followup_compliance = round(completed_todos * 100.0 / total_todos, 1) if total_todos else 100.0

    visas_count = 0
    completed_visas = 0
    if lead_names and has_doctype("Visa Application"):
        visas_count = frappe.db.count("Visa Application", {"lead": ["in", lead_names]})
        completed_visas = frappe.db.count("Visa Application", {"lead": ["in", lead_names], "status": "Completed"})

    total_leads = len(leads_data)
    converted_leads = sum(1 for l in leads_data if str(l.status or "").lower() in ("approved", "converted", "won"))
    lost_leads = sum(1 for l in leads_data if str(l.status or "").lower() == "lost")
    contacted_leads = len(set(filter(None, [c.lead for c in all_comm_events])))
    conversion_rate = round(converted_leads * 100.0 / total_leads, 1) if total_leads else 0.0
    business_performance_score = round((conversion_rate * 0.5) + (followup_compliance * 0.5), 1)

    coaching_tips = []
    ai_feedback_list = []
    for e in evaluations:
        if e.coaching_tips:
            coaching_tips.append(e.coaching_tips)
        if e.ai_feedback:
            ai_feedback_list.append(e.ai_feedback)
    for c in all_comm_events:
        if c.coaching_suggestion and c.coaching_suggestion not in coaching_tips:
            coaching_tips.append(c.coaching_suggestion)

    failed_jobs = frappe.get_all(
        "Lead Intake AI Job",
        filters={"state": "FAILED"},
        fields=["name", "queue", "last_error", "started_at"],
        order_by="started_at desc",
        limit_page_length=5,
    ) if has_doctype("Lead Intake AI Job") else []

    return {
        "employee": {
            "name": emp_doc.name,
            "employee_name": emp_doc.employee_name,
            "department": emp_doc.department,
            "designation": emp_doc.designation,
            "status": emp_doc.status,
            "user_id": emp_doc.user_id,
        },
        "period": {
            "preset": preset,
            "from_date": str(start_date),
            "to_date": str(end_date),
        },
        "summary": {
            "total_interactions": total_interactions,
            "unique_customers": unique_customers,
            "unique_leads": unique_leads,
            "channels": channel_counts,
        },
        "ai_metrics": {
            "overall_score": avg_ai_score,
            "insufficient_data": insufficient_data,
            "ai_evaluated": ai_evaluated,
            "ai_pending": ai_pending,
            "ai_failed": ai_failed,
            "ai_unavailable": ai_unavailable,
            "evaluated_percentage": round(ai_evaluated * 100.0 / total_interactions, 1) if total_interactions else 0.0,
            "dimensions": {
                "friendliness": friendliness,
                "empathy": empathy,
                "professionalism": professionalism,
                "clarity": clarity,
                "responsiveness": responsiveness,
                "policy_compliance": policy_compliance,
            },
        },
        "business_metrics": {
            "assigned_leads": total_leads,
            "contacted_leads": contacted_leads,
            "converted_leads": converted_leads,
            "lost_leads": lost_leads,
            "conversion_rate": conversion_rate,
            "business_score": business_performance_score,
            "followups_created": total_todos,
            "followups_completed": completed_todos,
            "followups_overdue": overdue_todos,
            "followup_compliance": followup_compliance,
            "visa_applications_created": visas_count,
            "visa_applications_completed": completed_visas,
        },
        "coaching": {
            "coaching_tips": coaching_tips[:10],
            "ai_feedback": ai_feedback_list[:10],
        },
        "data_quality": {
            "total_interactions": total_interactions,
            "ai_evaluated": ai_evaluated,
            "ai_pending": ai_pending,
            "ai_failed": ai_failed,
            "score_basis": f"Calculated from {ai_evaluated} AI-evaluated interactions" if ai_evaluated else "Insufficient AI evaluation data for this period",
            "failed_jobs": failed_jobs,
        },
        "top_cards": {
            "total_leads": total_leads,
            "active_leads": contacted_leads,
            "converted_leads": converted_leads,
            "conversion_rate": conversion_rate,
        },
        "communication_performance": {
            "followup_compliance": followup_compliance,
            "open_todos": total_todos - completed_todos,
            "overdue_todos": overdue_todos,
        },
        "ai_performance": {
            "overall_score": avg_ai_score,
            "insufficient_data": insufficient_data,
            "evaluations_count": ai_evaluated,
            "friendliness": friendliness,
            "empathy": empathy,
            "professionalism": professionalism,
        },
        "pipeline_health": {
            "total_queues": total_interactions,
            "action_required": ai_failed,
            "uncategorized_leads": 0,
            "failed_stages": ai_failed,
        },
        "generated_at": frappe.utils.now_datetime(),
    }


@frappe.whitelist()
def employee_interactions(
    employee,
    preset="this_month",
    from_date=None,
    to_date=None,
    lead_source=None,
    category=None,
    subcategory=None,
    visa_type=None,
    country=None,
    lead_status=None,
    channel=None,
    ai_status=None,
    start=0,
    page_length=20,
):
    from visa_crm.api.lead_permissions import require_management
    require_management()

    if not employee:
        frappe.throw("Employee parameter is required")

    start_date, end_date = _resolve_date_range(preset, from_date, to_date)
    emp_doc = frappe.get_doc("Employee", employee)
    emp_user_id = emp_doc.user_id

    comm_filters = {"employee": employee}
    if start_date and end_date:
        comm_filters["creation"] = ["between", [f"{start_date} 00:00:00", f"{end_date} 23:59:59"]]

    if channel:
        comm_filters["source"] = channel

    raw_events = frappe.get_all(
        "Communication Event",
        filters=comm_filters,
        fields=[
            "name", "creation", "event_datetime", "source", "event_type", "direction",
            "customer", "lead", "employee", "status", "sentiment", "lead_score", "ai_score",
            "duration", "summary", "coaching_suggestion"
        ],
        order_by="creation desc",
        page_length=0,
    )

    lead_map = {}
    if raw_events:
        lead_ids = list(set(filter(None, [c.lead for c in raw_events])))
        if lead_ids:
            lead_rows = frappe.get_all(
                "CRM Lead",
                filters={"name": ["in", lead_ids]},
                fields=["name", "lead_name", "first_name", "last_name", "mobile_no", "phone", "email", "source", "lead_category", "lead_group", "visa_type", "country_interested", "status"],
            )
            lead_map = {l.name: l for l in lead_rows}

    cust_map = {}
    if raw_events:
        cust_ids = list(set(filter(None, [c.customer for c in raw_events])))
        if cust_ids:
            cust_rows = frappe.get_all(
                "Customer",
                filters={"name": ["in", cust_ids]},
                fields=["name", "customer_name", "mobile_no", "email_id"],
            )
            cust_map = {c.name: c for c in cust_rows}

    eval_map = {}
    if raw_events:
        event_ids = [c.name for c in raw_events]
        eval_rows = frappe.get_all(
            "Employee Evaluation",
            filters={"communication_event": ["in", event_ids]},
            fields=["name", "communication_event", "overall_score", "friendliness", "empathy", "professionalism", "clarity", "responsiveness", "policy_compliance", "coaching_tips"],
        )
        eval_map = {e.communication_event: e for e in eval_rows}

    visa_map = {}
    if lead_map:
        visa_rows = frappe.get_all(
            "Visa Application",
            filters={"lead": ["in", list(lead_map.keys())]},
            fields=["name", "lead", "visa_type", "country_interested", "status"],
        )
        for v in visa_rows:
            visa_map[v.lead] = v

    ai_job_map = {}
    if has_doctype("Lead Intake AI Job") and raw_events:
        event_ids = [c.name for c in raw_events]
        j_rows = frappe.get_all(
            "Lead Intake AI Job",
            filters={"communication_event": ["in", event_ids]},
            fields=["communication_event", "state", "last_error"]
        )
        ai_job_map = {j.communication_event: j for j in j_rows}

    filtered_rows = []
    for c in raw_events:
        ld = lead_map.get(c.lead, frappe._dict())
        cust = cust_map.get(c.customer, frappe._dict())
        ev = eval_map.get(c.name)
        visa = visa_map.get(c.lead, frappe._dict())
        j_info = ai_job_map.get(c.name, frappe._dict())
        j_st = str(j_info.get("state") or "").upper()

        if lead_source and (ld.source or c.source) != lead_source:
            continue
        if category and category != "All" and ld.lead_category != category:
            continue
        if subcategory and subcategory not in ("All", "Unspecified") and ld.lead_group != subcategory:
            continue
        if visa_type and (ld.visa_type or visa.visa_type) != visa_type:
            continue
        if country and (ld.country_interested or visa.country_interested) != country:
            continue
        if lead_status and (ld.status or c.status) != lead_status:
            continue

        score = ev.overall_score if (ev and ev.overall_score is not None) else (c.ai_score if (c.ai_score is not None and c.ai_score > 0) else None)
        if score is not None:
            status_label = "Evaluated"
        elif j_st in ("FAILED", "ERROR") or str(c.status or "").lower() in ("failed", "error"):
            status_label = "Failed"
        elif j_st in ("RUNNING", "QUEUED", "PENDING") or str(c.status or "").lower() in ("pending", "running"):
            status_label = "Pending"
        else:
            status_label = "Unavailable"

        if ai_status and ai_status != "All" and status_label != ai_status:
            continue

        c_name = cust.customer_name or ld.lead_name or (f"{ld.first_name or ''} {ld.last_name or ''}".strip()) or "Unknown Customer"
        phone = cust.mobile_no or ld.mobile_no or ld.phone or ""
        email = cust.email_id or ld.email or ""

        filtered_rows.append({
            "name": c.name,
            "event_datetime": str(c.event_datetime or c.creation),
            "channel": c.source or c.event_type or "Unknown",
            "direction": c.direction or "Inbound",
            "customer": c.customer,
            "customer_name": c_name,
            "phone": phone,
            "email": email,
            "lead": c.lead,
            "visa_application": visa.name,
            "visa_type": visa.visa_type or ld.visa_type,
            "country_interested": visa.country_interested or ld.country_interested,
            "outcome": ld.status or c.status or "Open",
            "ai_status": status_label,
            "ai_score": score,
            "summary": c.summary or c.coaching_suggestion,
        })

    start = max(cint(start), 0)
    page_length = min(max(cint(page_length), 1), 100)
    paginated = filtered_rows[start : start + page_length]

    return {
        "interactions": paginated,
        "total_count": len(filtered_rows),
        "start": start,
        "page_length": page_length,
        "has_more": start + page_length < len(filtered_rows),
    }


@frappe.whitelist()
def employee_interaction_detail(communication_event):
    from visa_crm.api.lead_permissions import require_management
    require_management()

    if not communication_event or not frappe.db.exists("Communication Event", communication_event):
        frappe.throw("Communication Event not found", frappe.DoesNotExistError)

    comm = frappe.get_doc("Communication Event", communication_event)

    lead_doc = frappe.get_doc("CRM Lead", comm.lead) if comm.lead and frappe.db.exists("CRM Lead", comm.lead) else None
    cust_doc = frappe.get_doc("Customer", comm.customer) if comm.customer and frappe.db.exists("Customer", comm.customer) else None
    visa_doc = frappe.get_doc("Visa Application", {"lead": comm.lead}) if comm.lead and frappe.db.exists("Visa Application", {"lead": comm.lead}) else None

    eval_name = frappe.db.exists("Employee Evaluation", {"communication_event": communication_event})
    eval_doc = frappe.get_doc("Employee Evaluation", eval_name) if eval_name else None

    todos = frappe.get_all(
        "ToDo",
        filters={"reference_type": "CRM Lead", "reference_name": comm.lead},
        fields=["name", "description", "status", "date", "allocated_to"],
        order_by="creation desc",
    ) if comm.lead else []

    queue_info = None
    if has_doctype("Lead Intake Queue"):
        queue_name = frappe.db.get_value("Lead Intake Queue", {"communication_event": communication_event}, "name")
        if queue_name:
            q = frappe.get_doc("Lead Intake Queue", queue_name)
            queue_info = {
                "queue": q.name,
                "status": q.status,
                "ai_status": q.ai_status,
                "ai_error": q.ai_error,
                "ai_traceback": q.ai_traceback,
            }

    ai_job_info = None
    if has_doctype("Lead Intake AI Job"):
        job_name = frappe.db.get_value("Lead Intake AI Job", {"communication_event": communication_event}, "name")
        if job_name:
            j = frappe.get_doc("Lead Intake AI Job", job_name)
            ai_job_info = {
                "job_name": j.name,
                "state": j.state,
                "last_error": j.last_error,
                "last_traceback": j.last_traceback,
                "started_at": str(j.started_at) if j.started_at else None,
            }

    return {
        "communication_event": comm.as_dict(),
        "lead": lead_doc.as_dict() if lead_doc else None,
        "customer": cust_doc.as_dict() if cust_doc else None,
        "visa_application": visa_doc.as_dict() if visa_doc else None,
        "employee_evaluation": eval_doc.as_dict() if eval_doc else None,
        "todos": todos,
        "queue_info": queue_info,
        "ai_job_info": ai_job_info,
    }


def _resolve_date_range(preset, from_date, to_date):
    from frappe.utils import add_months, get_first_day, get_last_day, getdate, nowdate, today

    if preset == "today":
        return today(), today()
    elif preset == "this_week":
        curr = getdate(today())
        start = curr - frappe.utils.datetime.timedelta(days=curr.weekday())
        return str(start), today()
    elif preset == "this_month":
        return str(get_first_day(today())), today()
    elif preset == "last_month":
        last_m = add_months(get_first_day(today()), -1)
        return str(get_first_day(last_m)), str(get_last_day(last_m))
    elif from_date and to_date:
        return str(getdate(from_date)), str(getdate(to_date))
    elif from_date:
        return str(getdate(from_date)), today()
    else:
        return str(get_first_day(today())), today()
