import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
    _doctype()
    _queue_fields()
    _status_options()
    _page()
    frappe.db.commit()

def _doctype():
    if frappe.db.exists("DocType", "Meta Webhook Event"):
        return
    doc = frappe.get_doc({"doctype":"DocType","name":"Meta Webhook Event","module":"Visa CRM","custom":1,"is_submittable":0,"track_changes":1,"fields":[
        _field("event_type","Event Field","Data"),_field("leadgen_id","Leadgen ID","Data"),_field("page_id","Page ID","Data"),_field("form_id","Form ID","Data"),_field("received_at","Received At","Datetime"),_field("status","Status","Data"),_field("queue","Lead Intake Queue","Link","Lead Intake Queue"),_field("queue_status","Queue Status","Data"),_field("crm_lead","CRM Lead","Link","CRM Lead"),_field("graph_api_request","Graph API Request","Long Text"),_field("graph_api_response","Graph API Response","Long Text"),_field("request_headers","Request Headers","Long Text"),_field("raw_json","Raw JSON","Long Text")
    ],"permissions":[{"role":"System Manager","read":1,"write":1,"create":1,"delete":1},{"role":"Sales Manager","read":1},{"role":"Counselor","read":1}]})
    doc.insert(ignore_permissions=True)

def _field(fieldname,label,fieldtype,options=None):
    row={"fieldname":fieldname,"label":label,"fieldtype":fieldtype}
    if options:
        row["options"]=options
    return row

def _queue_fields():
    if not frappe.db.exists("DocType", "Lead Intake Queue"):
        return
    create_custom_fields({"Lead Intake Queue":[
        {"fieldname":"event_type","label":"Meta Event Field","fieldtype":"Data","insert_after":"source_lead_id"},
        {"fieldname":"meta_webhook_event","label":"Meta Webhook Event","fieldtype":"Link","options":"Meta Webhook Event","insert_after":"event_type"},
        {"fieldname":"graph_api_request","label":"Graph API Request","fieldtype":"Long Text","insert_after":"graph_payload"},
        {"fieldname":"graph_api_response","label":"Graph API Response","fieldtype":"Long Text","insert_after":"graph_api_request"},
        {"fieldname":"graph_http_status","label":"Graph HTTP Status","fieldtype":"Data","insert_after":"graph_api_response"},
        {"fieldname":"graph_fbtrace_id","label":"Graph fbtrace ID","fieldtype":"Data","insert_after":"graph_http_status"},
        {"fieldname":"graph_error_code","label":"Graph Error Code","fieldtype":"Data","insert_after":"graph_fbtrace_id"},
        {"fieldname":"graph_error_subcode","label":"Graph Error Subcode","fieldtype":"Data","insert_after":"graph_error_code"},
        {"fieldname":"graph_error_type","label":"Graph Error Type","fieldtype":"Data","insert_after":"graph_error_subcode"},
        {"fieldname":"graph_error_message","label":"Graph Error Message","fieldtype":"Small Text","insert_after":"graph_error_type"}
    ]}, update=True)

def _status_options():
    if not frappe.db.exists("DocType", "Lead Intake Queue"):
        return
    current = frappe.db.get_value("DocField", {"parent":"Lead Intake Queue","fieldname":"status"}, "options") or ""
    options = [row for row in current.splitlines() if row]
    if "Ignored Test Event" not in options:
        options.append("Ignored Test Event")
        frappe.db.set_value("DocField", {"parent":"Lead Intake Queue","fieldname":"status"}, "options", "\n".join(options), update_modified=False)

def _page():
    if frappe.db.exists("Page", "meta-live-monitor"):
        return
    frappe.get_doc({"doctype":"Page","page_name":"meta-live-monitor","title":"Meta Live Monitor","module":"Visa CRM","standard":"Yes"}).insert(ignore_permissions=True)
