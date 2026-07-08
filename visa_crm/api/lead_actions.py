import frappe
from visa_crm.api.document_checklist import generate_checklist
from visa_crm.api.lead_assignment import assign_lead
from visa_crm.api.crm_lifecycle import change_stage
from visa_crm.api.visa_application import create_for_lead

@frappe.whitelist()
def assign_counselor(lead):
    return assign_lead(lead)

@frappe.whitelist()
def change_status(lead, stage):
    return change_stage(lead, stage)

@frappe.whitelist()
def create_visa_application(lead):
    return create_for_lead(lead)

@frappe.whitelist()
def create_document_checklist(lead):
    return generate_checklist(lead)
