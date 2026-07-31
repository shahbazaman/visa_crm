import datetime
import frappe
from frappe.utils import getdate,now,now_datetime
from visa_crm.api.execution_history import record
from visa_crm.api.meta_utils import has_doctype,has_field,load_json,log_info,meta_debug_log,safe_json_dumps,set_if_has

def assign_lead(lead, queue_doc=None, strategy=None, context=None, communication_event=None):
    context = context or {}
    meta_debug_log("counselor_assignment_start", lead=lead, **context)
    queue_name=getattr(queue_doc,"name",None)
    existing=_existing_assignment(queue_name)
    employee,decision=(existing,{"strategy":"existing","selected":existing}) if existing else _select_employee(queue_doc,strategy)
    if not employee:
        log_info("meta_assignment_skipped", reason="no_employee", lead=lead)
        record(queue=queue_name,stage="COUNSELOR_ASSIGNMENT",execution_type="Stage",result="FAILED",failure_reason="No eligible counselor is configured",details=decision)
        meta_debug_log("counselor_assignment_end", lead=lead, employee=None, **context)
        return None
    if lead and has_doctype("CRM Lead"):
        doc = frappe.get_doc("CRM Lead", lead)
        for field in ("assigned_to", "assigned_employee", "counselor", "employee"):
            set_if_has(doc, field, employee)
        doc.save(ignore_permissions=True)
    _assignment_log(lead,employee,queue_name,communication_event,decision)
    _assignment_history(lead,employee,decision.get("strategy") or strategy or "least_workload",queue_name,communication_event,decision)
    if queue_doc:
        queue_doc.assigned_employee = employee
    log_info("meta_lead_assigned", lead=lead, employee=employee)
    record(queue=queue_name,stage="COUNSELOR_ASSIGNMENT",execution_type="Stage",result="SUCCESS",details=decision)
    meta_debug_log("counselor_assignment_end", lead=lead, employee=employee, **context)
    return employee

def _least_workload_employee(employees=None):
    employees = employees or _eligible_employees()
    if not employees:
        return None
    counts = {e: frappe.db.count("Lead Assignment", {"assigned_to": e, "status": ["in", ["Pending", "Accepted", "In Progress"]]}) for e in employees}
    return sorted(counts, key=lambda employee: (counts[employee], employee))[0]

def _round_robin_employee(employees=None):
    employees = employees or _eligible_employees()
    if not employees:
        return None
    last = frappe.get_all("Lead Assignment", fields=["assigned_to"], order_by="assigned_on desc", limit=1)
    if not last or last[0].assigned_to not in employees:
        return employees[0]
    return employees[(employees.index(last[0].assigned_to) + 1) % len(employees)]

def _eligible_employees():
    if not has_doctype("Employee"):
        return []
    configured = frappe.conf.get("visa_crm_sales_employees")
    if configured:
        return [employee for employee in configured if frappe.db.exists("Employee", employee)]
    filters = {"status": "Active"} if has_field("Employee", "status") else {}
    employees = frappe.get_all("Employee", filters=filters, pluck="name", order_by="name asc")
    groups = frappe.conf.get("visa_crm_sales_employee_groups") or []
    return _filter_by_groups(employees, groups) if groups else employees

def _filter_by_groups(employees, groups):
    if not has_doctype("Employee Group"):
        return employees
    linked = []
    for group in groups:
        for field in ("employee", "employee_name", "member"):
            if has_field("Employee Group", field):
                linked.extend(frappe.get_all("Employee Group", filters={"name": group}, pluck=field))
    return [employee for employee in employees if employee in linked] or employees

def _assignment_log(lead,employee,queue_name=None,communication_event=None,decision=None):
    if not lead or not employee or not has_doctype("Lead Assignment"):
        return
    key=f"assignment:{queue_name}" if queue_name else None
    existing=frappe.db.exists("Lead Assignment",{"meta_intake_key":key}) if key and has_field("Lead Assignment","meta_intake_key") else None
    existing = existing or frappe.db.exists("Lead Assignment", {"lead": lead, "assigned_to": employee, "status": ["in", ["Pending", "Accepted", "In Progress"]]})
    if existing:
        return
    doc = frappe.new_doc("Lead Assignment")
    doc.lead = lead
    doc.assigned_to = employee
    assigned_by = _link_value(doc, "assigned_by")
    if assigned_by:
        doc.assigned_by = assigned_by
    doc.assigned_on = now()
    doc.status = "Pending"
    doc.priority = "Medium"
    set_if_has(doc,"meta_intake_key",key)
    set_if_has(doc,"lead_intake_queue",queue_name)
    set_if_has(doc,"communication_event",communication_event)
    set_if_has(doc,"assignment_decision_json",safe_json_dumps(decision or {}))
    doc.insert(ignore_permissions=True)

def _assignment_history(lead,employee,strategy,queue_name=None,communication_event=None,decision=None):
    if not lead or not employee or not has_doctype("Counselor Assignment History"):
        return
    key=f"assignment-history:{queue_name}" if queue_name else None
    if key and has_field("Counselor Assignment History","meta_intake_key") and frappe.db.exists("Counselor Assignment History",{"meta_intake_key":key}):
        return
    doc = frappe.new_doc("Counselor Assignment History")
    for field,value in {"lead":lead,"assigned_to":employee,"assigned_by":_link_value(doc,"assigned_by"),"assigned_on":now(),"strategy":strategy,"meta_intake_key":key,"lead_intake_queue":queue_name,"communication_event":communication_event,"assignment_decision_json":safe_json_dumps(decision or {})}.items():
        set_if_has(doc, field, value)
    doc.insert(ignore_permissions=True)

def _link_value(doc, fieldname):
    field = doc.meta.get_field(fieldname)
    if not field or field.fieldtype != "Link" or not field.options:
        return frappe.session.user
    if field.options == "User":
        return frappe.session.user if frappe.db.exists("User", frappe.session.user) else None
    if field.options == "Employee":
        employee = _employee_for_user(frappe.session.user)
        return employee if employee and frappe.db.exists("Employee", employee) else None
    return frappe.session.user if frappe.db.exists(field.options, frappe.session.user) else None

def _employee_for_user(user):
    if not user or not has_doctype("Employee"):
        return None
    for field in ("user_id", "company_email", "personal_email"):
        if has_field("Employee", field):
            found = frappe.db.get_value("Employee", {field: user}, "name")
            if found:
                return found
    return None

def _existing_assignment(queue_name):
    if not queue_name or not has_doctype("Lead Assignment") or not has_field("Lead Assignment","meta_intake_key"):
        return None
    return frappe.db.get_value("Lead Assignment",{"meta_intake_key":f"assignment:{queue_name}"},"assigned_to")

def _select_employee(queue_doc=None,strategy=None):
    strategy=strategy or frappe.conf.get("visa_crm_assignment_strategy") or "least_workload"
    employees=_eligible_employees()
    data=load_json(getattr(queue_doc,"normalized_payload",None),{}) if queue_doc else {}
    language=data.get("language") or (data.get("meta_fields") or {}).get("language")
    country=data.get("country_interested") or data.get("destination")
    languages=frappe.conf.get("visa_crm_employee_languages") or {}
    countries=frappe.conf.get("visa_crm_employee_country_expertise") or {}
    candidates=[]
    for employee in employees:
        working=_is_working(employee)
        language_match=_matches_config(languages.get(employee),language)
        country_match=_matches_config(countries.get(employee),country)
        workload=frappe.db.count("Lead Assignment",{"assigned_to":employee,"status":["in",["Pending","Accepted","In Progress"]]}) if has_doctype("Lead Assignment") else 0
        candidates.append({"employee":employee,"working":working,"language_match":language_match,"country_match":country_match,"workload":workload})
    available=[row["employee"] for row in candidates if row["working"]]
    preferred=[row["employee"] for row in candidates if row["working"] and (not language or row["language_match"]) and (not country or row["country_match"])]
    pool=preferred or available
    fallback=frappe.conf.get("visa_crm_fallback_counselor")
    if not pool and fallback and frappe.db.exists("Employee",fallback):
        selected=fallback
        strategy_used="fallback"
    elif strategy=="round_robin":
        selected=_round_robin_employee(pool) if pool else None
        strategy_used="round_robin"
    else:
        selected=_least_workload_employee(pool) if pool else None
        strategy_used="least_workload"
    return selected,{"strategy":strategy_used,"requested_strategy":strategy,"selected":selected,"language":language,"country":country,"candidates":candidates,"fallback":fallback}

def _matches_config(configured,value):
    if not value:
        return True
    if not configured:
        return False
    values=configured if isinstance(configured,(list,tuple,set)) else str(configured).split(",")
    return str(value).strip().lower() in {str(row).strip().lower() for row in values}

def _is_working(employee):
    now_dt=now_datetime()
    if has_field("Employee","holiday_list"):
        holiday_list=frappe.db.get_value("Employee",employee,"holiday_list")
        if holiday_list and frappe.db.exists("Holiday",{"parent":holiday_list,"holiday_date":getdate(now_dt)}):
            return False
    hours=frappe.conf.get("visa_crm_working_hours") or {"start":"08:00","end":"20:00"}
    employee_hours=(frappe.conf.get("visa_crm_employee_working_hours") or {}).get(employee) or hours
    try:
        start=datetime.time.fromisoformat(employee_hours.get("start","08:00"))
        end=datetime.time.fromisoformat(employee_hours.get("end","20:00"))
        current=now_dt.time()
        return start<=current<=end if start<=end else current>=start or current<=end
    except Exception:
        return True
