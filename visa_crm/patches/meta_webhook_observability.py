import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
    if not frappe.db.exists("DocType", "Meta Webhook Event"):
        return
    create_custom_fields({"Meta Webhook Event":[{"fieldname":"entry_id","label":"Entry ID","fieldtype":"Data","insert_after":"event_type"}]}, update=True)
