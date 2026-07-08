import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

DOCTYPE_FIELDS = {
    "Visa Application": [("lead", "Link", "CRM Lead"), ("customer", "Link", "Customer"), ("applicant_name", "Data", None), ("visa_type", "Data", None), ("country", "Data", None), ("status", "Select", "Draft\nDocuments Pending\nUnder Verification\nVisa Processing\nSubmitted\nApproved\nRejected\nCancelled"), ("submitted_on", "Date", None), ("decision_on", "Date", None), ("remarks", "Small Text", None)],
    "Customer Documents": [("lead", "Link", "CRM Lead"), ("customer", "Link", "Customer"), ("visa_application", "Link", "Visa Application"), ("document_type", "Data", None), ("status", "Select", "Pending\nReceived\nVerified\nRejected"), ("attachment", "Attach", None), ("visa_type", "Data", None), ("country", "Data", None), ("received_on", "Date", None), ("remarks", "Small Text", None)],
    "Follow-up History": [("lead", "Link", "CRM Lead"), ("customer", "Link", "Customer"), ("todo", "Link", "ToDo"), ("follow_up_date", "Date", None), ("status", "Select", "Open\nCompleted\nOverdue\nEscalated"), ("rule", "Data", None), ("remarks", "Small Text", None)],
    "Counselor Assignment History": [("lead", "Link", "CRM Lead"), ("assigned_to", "Link", "Employee"), ("assigned_by", "Link", "User"), ("assigned_on", "Datetime", None), ("strategy", "Data", None), ("remarks", "Small Text", None)],
    "Lead Timeline": [("lead", "Link", "CRM Lead"), ("stage", "Data", None), ("event_type", "Data", None), ("description", "Long Text", None), ("event_datetime", "Datetime", None), ("created_by", "Link", "User")],
    "Activity Log": [("lead", "Link", "CRM Lead"), ("activity_type", "Data", None), ("description", "Long Text", None), ("activity_datetime", "Datetime", None), ("owner_user", "Link", "User")],
    "Payment Schedule": [("lead", "Link", "CRM Lead"), ("customer", "Link", "Customer"), ("visa_application", "Link", "Visa Application"), ("amount", "Currency", None), ("due_date", "Date", None), ("status", "Select", "Pending\nPaid\nOverdue\nCancelled"), ("paid_on", "Date", None), ("remarks", "Small Text", None)],
    "Visa Status Log": [("lead", "Link", "CRM Lead"), ("visa_application", "Link", "Visa Application"), ("from_stage", "Data", None), ("to_stage", "Data", None), ("changed_by", "Link", "User"), ("changed_on", "Datetime", None), ("remarks", "Small Text", None)]
}

def execute():
    for doctype, fields in DOCTYPE_FIELDS.items():
        _ensure_doctype(doctype, fields)
    _lead_fields()

def _ensure_doctype(name, fields):
    if frappe.db.exists("DocType", name):
        rows = [_custom_field(field) for field in fields if not frappe.get_meta(name).has_field(field[0]) and _target_ok(field)]
        if rows:
            create_custom_fields({name: rows}, update=True)
        return
    doc = frappe.get_doc({"doctype": "DocType", "name": name, "module": "Visa CRM", "custom": 1, "is_submittable": 0, "autoname": "hash", "fields": [_field(field) for field in fields], "permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1, "submit": 0, "cancel": 0, "amend": 0}]})
    doc.insert(ignore_permissions=True)

def _field(spec):
    fieldname, fieldtype, options = spec
    return {"fieldname": fieldname, "label": fieldname.replace("_", " ").title(), "fieldtype": fieldtype, "options": options}

def _custom_field(spec):
    fieldname, fieldtype, options = spec
    return {"fieldname": fieldname, "label": fieldname.replace("_", " ").title(), "fieldtype": fieldtype, "options": options}

def _target_ok(spec):
    return spec[1] != "Link" or not spec[2] or frappe.db.exists("DocType", spec[2])

def _lead_fields():
    if not frappe.db.exists("DocType", "CRM Lead"):
        return
    create_custom_fields({"CRM Lead": [
        {"fieldname": "workflow_stage", "label": "Workflow Stage", "fieldtype": "Select", "options": "New\nAssigned\nContacted\nInterested\nDocuments Pending\nDocuments Received\nUnder Verification\nVisa Processing\nSubmitted\nApproved\nRejected\nCancelled\nLost", "insert_after": "status"},
        {"fieldname": "assigned_employee", "label": "Assigned Employee", "fieldtype": "Link", "options": "Employee", "insert_after": "workflow_stage"},
        {"fieldname": "visa_type", "label": "Visa Type", "fieldtype": "Data", "insert_after": "assigned_employee"},
        {"fieldname": "country_interested", "label": "Country Interested", "fieldtype": "Data", "insert_after": "visa_type"}
    ]}, update=True)
