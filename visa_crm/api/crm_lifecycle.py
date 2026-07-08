import frappe
from frappe.utils import add_days, now, today
from visa_crm.api.meta_utils import has_doctype, has_field, set_if_has

STAGES = ["New", "Assigned", "Contacted", "Interested", "Documents Pending", "Documents Received", "Under Verification", "Visa Processing", "Submitted", "Approved", "Rejected", "Cancelled", "Lost"]
TERMINAL = {"Approved", "Rejected", "Cancelled", "Lost"}
FOLLOWUP_RULES = [1, 3, 7]

def change_stage(lead, stage, note=None, user=None):
    doc = frappe.get_doc("CRM Lead", lead)
    old = _stage(doc)
    validate_transition(old, stage)
    _set_stage(doc, stage)
    doc.save(ignore_permissions=True)
    log_stage_change(lead, old, stage, note, user)
    create_stage_side_effects(doc, old, stage)
    return doc.name

def validate_transition(old, new):
    if old == new:
        return
    if old in TERMINAL:
        frappe.throw(f"Cannot move lead from terminal stage {old}")
    if new not in STAGES:
        frappe.throw(f"Invalid lead stage {new}")
    if old and old in STAGES and STAGES.index(new) > STAGES.index(old) + 1:
        frappe.throw(f"Cannot skip mandatory stages from {old} to {new}")

def validate_lead_transition(doc, method=None):
    before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else getattr(doc, "_doc_before_save", None)
    old = _stage(before) if before else None
    new = _stage(doc)
    if old and new and old != new:
        validate_transition(old, new)

def on_lead_update(doc, method=None):
    before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else getattr(doc, "_doc_before_save", None)
    old = _stage(before) if before else None
    new = _stage(doc)
    if old and new and old != new:
        log_stage_change(doc.name, old, new)
        create_stage_side_effects(doc, old, new)

def create_stage_side_effects(lead_doc, old, new):
    create_timeline(lead_doc.name, f"Stage changed from {old or 'None'} to {new}", new)
    create_activity(lead_doc.name, "Stage Change", f"{old or 'None'} -> {new}")
    create_communication(lead_doc, new)
    if new == "Documents Pending":
        from visa_crm.api.document_checklist import generate_checklist
        generate_checklist(lead_doc.name)
    create_followups(lead_doc, new)
    notify_stage_change(lead_doc, new)

def log_stage_change(lead, old, new, note=None, user=None):
    if not has_doctype("Visa Status Log"):
        return
    doc = frappe.new_doc("Visa Status Log")
    _set_many(doc, {"lead": lead, "from_stage": old, "to_stage": new, "changed_by": user or frappe.session.user, "changed_on": now(), "remarks": note})
    doc.insert(ignore_permissions=True)

def create_timeline(lead, message, stage=None):
    if not has_doctype("Lead Timeline"):
        return None
    doc = frappe.new_doc("Lead Timeline")
    _set_many(doc, {"lead": lead, "stage": stage, "event_type": "Workflow", "description": message, "event_datetime": now(), "created_by": frappe.session.user})
    doc.insert(ignore_permissions=True)
    return doc.name

def create_activity(lead, activity_type, description):
    if not has_doctype("Activity Log"):
        return None
    doc = frappe.new_doc("Activity Log")
    _set_many(doc, {"lead": lead, "activity_type": activity_type, "description": description, "activity_datetime": now(), "owner_user": frappe.session.user})
    doc.insert(ignore_permissions=True)
    return doc.name

def create_communication(lead_doc, stage):
    if not has_doctype("Communication Event"):
        return None
    event_id = f"stage:{lead_doc.name}:{stage}"
    if frappe.db.exists("Communication Event", {"event_id": event_id}):
        return frappe.db.get_value("Communication Event", {"event_id": event_id}, "name")
    doc = frappe.new_doc("Communication Event")
    _set_many(doc, {"event_id": event_id, "source": "Manual", "event_type": "Note", "direction": "Outbound", "lead": lead_doc.name, "summary": f"Lead moved to {stage}", "event_datetime": now()})
    doc.insert(ignore_permissions=True)
    return doc.name

def create_followups(lead_doc, stage):
    if stage in TERMINAL:
        return []
    names = []
    for days in _followup_rules():
        names.append(_todo(lead_doc, days, stage))
    return [name for name in names if name]

def notify_stage_change(lead_doc, stage):
    if not has_doctype("Notification Log"):
        return
    user = _assigned_user(lead_doc)
    if not user:
        return
    doc = frappe.new_doc("Notification Log")
    _set_many(doc, {"subject": f"Lead {lead_doc.name} moved to {stage}", "type": "Alert", "for_user": user, "document_type": "CRM Lead", "document_name": lead_doc.name})
    doc.insert(ignore_permissions=True)

def process_overdue_followups():
    for todo in frappe.get_all("ToDo", filters={"status": "Open", "date": ["<", today()]}, fields=["name", "reference_type", "reference_name", "allocated_to"]):
        if todo.reference_type == "CRM Lead":
            create_activity(todo.reference_name, "Overdue Follow-up", f"ToDo {todo.name} is overdue")
            _notify_user(todo.allocated_to, f"Overdue follow-up for {todo.reference_name}", "ToDo", todo.name)

def document_request(lead, documents):
    lead_doc = frappe.get_doc("CRM Lead", lead)
    create_activity(lead, "Document Request", ", ".join(documents))
    _notify_user(_assigned_user(lead_doc), f"Documents requested for {lead}", "CRM Lead", lead)

def _todo(lead_doc, days, stage):
    key = f"{lead_doc.name}:{stage}:{days}"
    if frappe.db.exists("ToDo", {"reference_type": "CRM Lead", "reference_name": lead_doc.name, "description": ["like", f"%{key}%"]}):
        return None
    doc = frappe.new_doc("ToDo")
    doc.description = f"Follow up lead {lead_doc.name} after {days} day(s)\nRule:{key}"
    doc.date = add_days(today(), days)
    doc.allocated_to = _assigned_user(lead_doc)
    doc.reference_type = "CRM Lead"
    doc.reference_name = lead_doc.name
    doc.insert(ignore_permissions=True)
    if has_doctype("Follow-up History"):
        hist = frappe.new_doc("Follow-up History")
        _set_many(hist, {"lead": lead_doc.name, "follow_up_date": doc.date, "status": "Open", "todo": doc.name, "rule": f"{days} days"})
        hist.insert(ignore_permissions=True)
    return doc.name

def _followup_rules():
    rules = frappe.conf.get("visa_crm_followup_rules") or FOLLOWUP_RULES
    return [int(day) for day in rules]

def _stage(doc):
    if not doc:
        return None
    for field in ("workflow_stage", "workflow_state", "stage", "status"):
        if hasattr(doc, field) and getattr(doc, field):
            return getattr(doc, field)
    return None

def _set_stage(doc, stage):
    for field in ("workflow_stage", "workflow_state", "stage", "status"):
        if doc.meta.has_field(field):
            doc.set(field, stage)
            return

def _assigned_user(doc):
    for field in ("assigned_to", "owner"):
        if getattr(doc, field, None):
            return getattr(doc, field)
    for field in ("assigned_employee", "counselor", "employee"):
        employee = getattr(doc, field, None)
        if employee and has_field("Employee", "user_id"):
            return frappe.db.get_value("Employee", employee, "user_id")
    return None

def _notify_user(user, subject, doctype, name):
    if not user or not has_doctype("Notification Log"):
        return
    doc = frappe.new_doc("Notification Log")
    _set_many(doc, {"subject": subject, "type": "Alert", "for_user": user, "document_type": doctype, "document_name": name})
    doc.insert(ignore_permissions=True)

def _set_many(doc, values):
    for field, value in values.items():
        set_if_has(doc, field, value)
