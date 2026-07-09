import frappe
from visa_crm.api.meta_utils import has_doctype, has_field

INDEXES={
    "Lead Intake Queue":[(["status"],"idx_vc_liq_status"),(["source_lead_id"],"idx_vc_liq_source_lead_id"),(["status","creation"],"idx_vc_liq_status_creation"),(["status","next_retry_at"],"idx_vc_liq_retry")],
    "Communication Event":[(["event_id"],"idx_vc_ce_event_id"),(["customer"],"idx_vc_ce_customer"),(["lead"],"idx_vc_ce_lead"),(["event_datetime"],"idx_vc_ce_event_datetime"),(["conversation_status"],"idx_vc_ce_conversation_status")],
    "CRM Lead":[(["mobile_no"],"idx_vc_crm_lead_mobile"),(["email"],"idx_vc_crm_lead_email"),(["workflow_stage"],"idx_vc_crm_lead_stage"),(["assigned_employee"],"idx_vc_crm_lead_employee")],
    "Customer":[(["mobile_no"],"idx_vc_customer_mobile"),(["email_id"],"idx_vc_customer_email"),(["whatsapp_no"],"idx_vc_customer_whatsapp")],
    "ToDo":[(["status","date"],"idx_vc_todo_status_date")]
}

def execute():
    for doctype, indexes in INDEXES.items():
        if not has_doctype(doctype):
            continue
        for fields, name in indexes:
            if all(has_field(doctype, field) for field in fields):
                _add_index(doctype, fields, name)
    frappe.logger("visa_crm.migration").info("Visa CRM performance/security audit patch completed")

def _add_index(doctype, fields, name):
    try:
        frappe.db.add_index(doctype, fields, index_name=name)
    except Exception:
        frappe.logger("visa_crm.migration").warning(f"Skipped index {name}: {frappe.get_traceback()}")
