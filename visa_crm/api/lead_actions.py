import frappe
from visa_crm.api.document_checklist import generate_checklist
from visa_crm.api.lead_assignment import assign_lead
from visa_crm.api.crm_lifecycle import change_stage
from visa_crm.api.visa_application import create_for_lead

@frappe.whitelist()
def assign_counselor(lead):
    _staff()
    return assign_lead(lead)

@frappe.whitelist()
def change_status(lead, stage):
    _staff()
    return change_stage(lead, stage)

@frappe.whitelist()
def create_visa_application(lead):
    _staff()
    return create_for_lead(lead)

@frappe.whitelist()
def create_document_checklist(lead):
    _staff()
    return generate_checklist(lead)

def _staff():
    if frappe.session.user=="Guest" or not ({"System Manager","Sales Manager","Counselor","Visa Processing","Administrator"} & set(frappe.get_roles())):
        frappe.throw("Visa CRM staff access required", frappe.PermissionError)
