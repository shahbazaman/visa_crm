import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

FIELDS=(
    {"fieldname":"ai_status","label":"AI Status","fieldtype":"Select","options":"Pending\nQueued\nCompleted\nFailed","insert_after":"followup_reference"},
    {"fieldname":"ai_error","label":"AI Error","fieldtype":"Long Text","insert_after":"ai_status"},
    {"fieldname":"ai_traceback","label":"AI Traceback","fieldtype":"Code","options":"Python","insert_after":"ai_error"},
    {"fieldname":"ai_retry_count","label":"AI Retry Count","fieldtype":"Int","default":"0","insert_after":"ai_traceback"}
)

def execute():
    if not frappe.db.exists("DocType","Lead Intake Queue"):
        return
    for field in FIELDS:
        if frappe.db.exists("DocField",{"parent":"Lead Intake Queue","fieldname":field["fieldname"]}) or frappe.db.exists("Custom Field",{"dt":"Lead Intake Queue","fieldname":field["fieldname"]}):
            continue
        create_custom_field("Lead Intake Queue",field)
    frappe.clear_cache(doctype="Lead Intake Queue")
    frappe.db.commit()
