import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
    if frappe.db.exists("DocType", "Lead Intake Queue"):
        options = "Lead Received\nFetching Meta Lead\nLead Downloaded\nDuplicate Found\nCustomer Matched\nLead Created\nAssigned\nFollowup Created\nProcessed\nFailed"
        frappe.db.set_value("DocField", {"parent": "Lead Intake Queue", "fieldname": "status"}, "options", options, update_modified=False)
        frappe.db.sql("""update `tabLead Intake Queue` set status='Lead Received' where status='Pending Processing'""")
        frappe.db.sql("""update `tabLead Intake Queue` set status='Failed' where status='Retrying'""")
        frappe.db.sql("""update `tabLead Intake Queue` set status='Processed' where status='Completed'""")
    create_custom_fields({"Lead Intake Queue": [
        {"fieldname": "retry_count", "label": "Retry Count", "fieldtype": "Int", "insert_after": "assigned_employee"},
        {"fieldname": "last_error", "label": "Last Error", "fieldtype": "Small Text", "insert_after": "retry_count"},
        {"fieldname": "next_retry_at", "label": "Next Retry At", "fieldtype": "Datetime", "insert_after": "last_error"},
        {"fieldname": "processing_started_at", "label": "Processing Started At", "fieldtype": "Datetime", "insert_after": "next_retry_at"},
        {"fieldname": "processing_completed_at", "label": "Processing Completed At", "fieldtype": "Datetime", "insert_after": "processing_started_at"},
        {"fieldname": "graph_payload", "label": "Graph Payload", "fieldtype": "Long Text", "insert_after": "raw_payload"},
        {"fieldname": "custom_answers", "label": "Custom Answers", "fieldtype": "Long Text", "insert_after": "graph_payload"},
        {"fieldname": "page_id", "label": "Page ID", "fieldtype": "Data", "insert_after": "source_lead_id"},
        {"fieldname": "form_id", "label": "Form ID", "fieldtype": "Data", "insert_after": "page_id"},
        {"fieldname": "campaign_id", "label": "Campaign ID", "fieldtype": "Data", "insert_after": "campaign_name"},
        {"fieldname": "adset_id", "label": "Adset ID", "fieldtype": "Data", "insert_after": "adset_name"},
        {"fieldname": "ad_id", "label": "Ad ID", "fieldtype": "Data", "insert_after": "ad_name"},
        {"fieldname": "communication_event", "label": "Communication Event", "fieldtype": "Link", "options": "Communication Event", "insert_after": "assigned_employee"},
        {"fieldname": "followup_reference", "label": "Follow-up Reference", "fieldtype": "Link", "options": "ToDo", "insert_after": "communication_event"}
    ]}, update=True)
    duplicates = frappe.db.sql("""select source_lead_id,count(*) from `tabLead Intake Queue` where ifnull(source_lead_id,'')!='' group by source_lead_id having count(*)>1 limit 1""")
    blanks = frappe.db.sql("""select count(*) from `tabLead Intake Queue` where ifnull(source_lead_id,'')=''""")[0][0]
    if duplicates or blanks:
        frappe.logger("visa_crm.meta").warning("Skipped unique source_lead_id index because duplicate Lead Intake Queue rows already exist")
        return
    try:
        frappe.db.add_unique("Lead Intake Queue", ["source_lead_id"], constraint_name="uniq_meta_source_lead_id")
    except Exception:
        frappe.logger("visa_crm.meta").warning(frappe.get_traceback())
