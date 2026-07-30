import frappe
from frappe.utils import add_days, today
from visa_crm.api.meta_utils import has_doctype, has_field, meta_debug_log, set_if_has

def create_meta_followup(data, lead=None, customer=None, employee=None, queue_name=None, context=None):
    context = context or {}
    meta_debug_log("todo_creation_start", lead=lead, customer=customer, employee=employee, **context)
    todo = _todo(data, lead, customer, employee, queue_name)
    _reminder(data, lead, customer, employee, queue_name)
    _activity(data, lead, customer, employee, queue_name)
    meta_debug_log("todo_creation_end", lead=lead, customer=customer, employee=employee, todo=todo, **context)
    return todo

def create_followup(ci):
    if ci.followup_created:
        return
    todo = frappe.new_doc("ToDo")
    todo.description = f"Call customer\n\n{ci.customer_name}\n\nVisa\n\n{ci.visa_type}\n\nIntent\n\n{ci.lead_intent}"
    todo.date = add_days(today(), 1)
    todo.insert()
    ci.followup_created = 1
    ci.followup_reference = todo.name
    ci.save()

def _todo(data, lead, customer, employee, queue_name):
    description = f"Follow up Meta lead: {data.get('customer_name') or lead or customer}\nPhone: {data.get('phone') or ''}\nEmail: {data.get('email') or ''}\nVisa: {data.get('visa_type') or ''}\nCountry: {data.get('country_interested') or ''}"
    key=f"followup:{queue_name}"
    existing=frappe.db.get_value("ToDo",{"meta_intake_key":key},"name") if has_field("ToDo","meta_intake_key") else None
    existing=existing or frappe.db.get_value("ToDo",{"reference_type":"Lead Intake Queue","reference_name":queue_name},"name")
    if existing:
        if has_field("ToDo","meta_intake_key") and not frappe.db.get_value("ToDo",existing,"meta_intake_key"):
            frappe.db.set_value("ToDo",existing,"meta_intake_key",key,update_modified=False)
        return existing
    todo = frappe.new_doc("ToDo")
    todo.description = description
    todo.date = add_days(today(), 1)
    todo.allocated_to = _employee_user(employee)
    todo.reference_type = "Lead Intake Queue"
    todo.reference_name = queue_name
    set_if_has(todo,"meta_intake_key",key)
    todo.insert(ignore_permissions=True)
    return todo.name

def _reminder(data, lead, customer, employee, queue_name):
    if not has_doctype("Reminder Scheduler"):
        return None
    key=f"reminder:{queue_name}"
    if has_field("Reminder Scheduler","meta_intake_key"):
        existing=frappe.db.get_value("Reminder Scheduler",{"meta_intake_key":key},"name")
        if existing:
            return existing
    if has_field("Reminder Scheduler","reference_doctype") and has_field("Reminder Scheduler","reference_name"):
        existing=frappe.db.get_value("Reminder Scheduler",{"reference_doctype":"Lead Intake Queue","reference_name":queue_name},"name")
        if existing:
            if has_field("Reminder Scheduler","meta_intake_key"):
                frappe.db.set_value("Reminder Scheduler",existing,"meta_intake_key",key,update_modified=False)
            return existing
    doc = frappe.new_doc("Reminder Scheduler")
    for field, value in {"lead": lead, "customer": customer, "employee": employee, "reference_doctype": "Lead Intake Queue", "reference_name": queue_name, "reminder_date": add_days(today(), 1), "status": "Open", "description": f"Follow up Meta lead {data.get('customer_name') or ''}","meta_intake_key":key}.items():
        set_if_has(doc, field, value)
    doc.insert(ignore_permissions=True)
    return doc.name

def _activity(data, lead, customer, employee, queue_name):
    if not has_doctype("Activity Timeline"):
        return None
    key=f"activity:{queue_name}"
    if has_field("Activity Timeline","meta_intake_key"):
        existing=frappe.db.get_value("Activity Timeline",{"meta_intake_key":key},"name")
        if existing:
            return existing
    if has_field("Activity Timeline","reference_doctype") and has_field("Activity Timeline","reference_name"):
        existing=frappe.db.get_value("Activity Timeline",{"reference_doctype":"Lead Intake Queue","reference_name":queue_name},"name")
        if existing:
            if has_field("Activity Timeline","meta_intake_key"):
                frappe.db.set_value("Activity Timeline",existing,"meta_intake_key",key,update_modified=False)
            return existing
    doc = frappe.new_doc("Activity Timeline")
    for field, value in {"lead": lead, "customer": customer, "employee": employee, "reference_doctype": "Lead Intake Queue", "reference_name": queue_name, "activity_type": "Meta Lead Intake", "description": f"Meta lead queued and follow-up created for {data.get('customer_name') or ''}","meta_intake_key":key}.items():
        set_if_has(doc, field, value)
    doc.insert(ignore_permissions=True)
    return doc.name

def _employee_user(employee):
    if employee and has_field("Employee", "user_id"):
        return frappe.db.get_value("Employee", employee, "user_id")
    return None
