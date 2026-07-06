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
    filters = {"status": "Active"} if has_field("Employee", "status") else {}
    return frappe.get_all("Employee", filters=filters, pluck="name", order_by="name asc")

def _assignment_log(lead, employee):
    if not lead or not employee or not has_doctype("Lead Assignment"):
        return
    existing = frappe.db.exists("Lead Assignment", {"lead": lead, "assigned_to": employee, "status": ["in", ["Pending", "Accepted", "In Progress"]]})
    if existing:
        return
    doc = frappe.new_doc("Lead Assignment")
    doc.lead = lead
    doc.assigned_to = employee
    doc.assigned_by = frappe.session.user
    doc.assigned_on = now()
    doc.status = "Pending"
    doc.priority = "Medium"
    doc.insert(ignore_permissions=True)
