import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field
from visa_crm.api.meta_utils import has_doctype,has_field

def execute():
    if has_doctype("CRM Lead") and not has_field("CRM Lead","assignment_status"):
        insert_after=next((field for field in ("assigned_counselor","assigned_employee","facebook_lead_id") if has_field("CRM Lead",field)),None)
        create_custom_field("CRM Lead",{"fieldname":"assignment_status","label":"Assignment Status","fieldtype":"Select","options":"Unassigned\nAssigned\nNeeds Assignment","default":"Unassigned","insert_after":insert_after})
    frappe.clear_cache(doctype="CRM Lead")
    frappe.db.commit()
