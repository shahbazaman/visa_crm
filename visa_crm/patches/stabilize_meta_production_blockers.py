import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

QUEUE_STATUSES="Lead Received\nPending Processing\nFetching Meta Lead\nLead Downloaded\nDuplicate Found\nCustomer Matched\nLead Created\nAssigned\nFollowup Created\nCompleted\nProcessed\nFailed\nRetrying\nIgnored Test Event"

def execute():
    if frappe.db.exists("DocType","Lead Intake Queue"):
        frappe.db.set_value("DocField",{"parent":"Lead Intake Queue","fieldname":"status"},"options",QUEUE_STATUSES,update_modified=False)
        frappe.db.set_value("DocField",{"parent":"Lead Intake Queue","fieldname":"source_lead_id"},"unique",1,update_modified=False)
        _queue_identity_index()
        _backfill_lead_identity()
        frappe.clear_cache(doctype="Lead Intake Queue")
    if frappe.db.exists("DocType","Customer") and not frappe.get_meta("Customer").has_field("crm_lead"):
        create_custom_field("Customer",{"fieldname":"crm_lead","label":"Primary CRM Lead","fieldtype":"Link","options":"CRM Lead","insert_after":"customer_name"})
        frappe.clear_cache(doctype="Customer")
    frappe.db.commit()

def _queue_identity_index():
    indexes=frappe.db.sql("show index from `tabLead Intake Queue`",as_dict=True)
    if any(row.Column_name=="source_lead_id" and not row.Non_unique for row in indexes):
        return
    duplicates=frappe.db.sql("""select source_lead_id,count(*) total from `tabLead Intake Queue` where ifnull(source_lead_id,'')!='' group by source_lead_id having count(*)>1 limit 1""",as_dict=True)
    if duplicates:
        frappe.logger("visa_crm.meta").error({"event":"queue_identity_index_skipped","duplicate_source_lead_id":duplicates[0].source_lead_id,"count":duplicates[0].total})
        return
    frappe.db.sql("""update `tabLead Intake Queue` set source_lead_id=null where source_lead_id=''""")
    frappe.db.add_unique("Lead Intake Queue",["source_lead_id"],"uniq_meta_source_lead_id")

def _backfill_lead_identity():
    if not frappe.db.exists("DocType","CRM Lead") or not frappe.get_meta("CRM Lead").has_field("facebook_lead_id"):
        return
    rows=frappe.get_all("Lead Intake Queue",filters={"matched_lead":["is","set"],"source_lead_id":["is","set"]},fields=["matched_lead","source_lead_id","form_id"],limit_page_length=0)
    for row in rows:
        current=frappe.db.get_value("CRM Lead",row.matched_lead,["facebook_lead_id","facebook_form_id"],as_dict=True)
        if not current or current.facebook_lead_id:
            continue
        owner=frappe.db.get_value("CRM Lead",{"facebook_lead_id":row.source_lead_id},"name")
        if owner and owner!=row.matched_lead:
            frappe.logger("visa_crm.meta").error({"event":"lead_identity_backfill_skipped","source_lead_id":row.source_lead_id,"matched_lead":row.matched_lead,"existing_lead":owner})
            continue
        values={"facebook_lead_id":row.source_lead_id}
        if row.form_id and not current.facebook_form_id:
            values["facebook_form_id"]=row.form_id
        frappe.db.set_value("CRM Lead",row.matched_lead,values,update_modified=False)
