import frappe
from frappe.utils import now
from visa_crm.api.meta_utils import has_doctype, has_field, log_info, meta_debug_log, set_if_has

def assign_lead(lead, queue_doc=None, strategy=None, context=None):
    context = context or {}
    meta_debug_log("counselor_assignment_start", lead=lead, **context)
    employee = _least_workload_employee() if (strategy or "least_workload") == "least_workload" else _round_robin_employee()
    if not employee:
        log_info("meta_assignment_skipped", reason="no_employee", lead=lead)
        meta_debug_log("counselor_assignment_end", lead=lead, employee=None, **context)
        return None
    if lead and has_doctype("CRM Lead"):
        doc = frappe.get_doc("CRM Lead", lead)
        for field in ("assigned_to", "assigned_employee", "counselor", "employee"):
            set_if_has(doc, field, employee)
        doc.save(ignore_permissions=True)
    _assignment_log(lead, employee)
    _assignment_history(lead, employee, strategy or "least_workload")
    if queue_doc:
        queue_doc.assigned_employee = employee
    log_info("meta_lead_assigned", lead=lead, employee=employee)
    meta_debug_log("counselor_assignment_end", lead=lead, employee=employee, **context)
    return employee

def _least_workload_employee():
    employees = _eligible_employees()
    if not employees:
        return None
    counts = {e: frappe.db.count("Lead Assignment", {"assigned_to": e, "status": ["in", ["Pending", "Accepted", "In Progress"]]}) for e in employees}
    return sorted(counts, key=lambda employee: (counts[employee], employee))[0]

def _round_robin_employee():
    employees = _eligible_employees()
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

def _assignment_log(lead, employee):
    if not lead or not employee or not has_doctype("Lead Assignment"):
        return
    existing = frappe.db.exists("Lead Assignment", {"lead": lead, "assigned_to": employee, "status": ["in", ["Pending", "Accepted", "In Progress"]]})
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
    doc.insert(ignore_permissions=True)

def _assignment_history(lead, employee, strategy):
    if not lead or not employee or not has_doctype("Counselor Assignment History"):
        return
    doc = frappe.new_doc("Counselor Assignment History")
    for field, value in {"lead": lead, "assigned_to": employee, "assigned_by": _link_value(doc, "assigned_by"), "assigned_on": now(), "strategy": strategy}.items():
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
