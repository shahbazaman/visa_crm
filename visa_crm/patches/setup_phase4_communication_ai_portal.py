import frappe

FIELDS=[
    ("provider","Data","Provider"),
    ("provider_message_id","Data","Provider Message ID"),
    ("parent_conversation_id","Data","Conversation ID"),
    ("assigned_user","Link","Assigned User","User"),
    ("conversation_status","Select","Conversation Status",None,"Open\nPending\nResolved\nArchived"),
    ("unread","Check","Unread"),
    ("label","Data","Label"),
    ("internal_notes","Long Text","Internal Notes"),
    ("attachments","Long Text","Attachments"),
    ("raw_channel_payload","Long Text","Raw Channel Payload"),
    ("deal","Link","Deal","CRM Deal"),
    ("visa_application","Link","Visa Application","Visa Application"),
    ("ai_next_best_action","Long Text","AI Next Best Action"),
    ("ai_followup_suggestion","Long Text","AI Follow-up Suggestion"),
    ("ai_lost_lead_analysis","Long Text","AI Lost Lead Analysis"),
    ("ai_employee_coaching","Long Text","AI Employee Coaching"),
    ("ai_manager_summary","Long Text","AI Manager Summary"),
    ("ai_reminder_suggestion","Long Text","AI Reminder Suggestion"),
    ("ai_customer_priority","Int","AI Customer Priority"),
    ("ai_visa_recommendation","Long Text","AI Visa Recommendation"),
    ("ai_quality_analysis","Long Text","AI Quality Analysis"),
    ("ai_timeline_summary","Long Text","AI Timeline Summary")
]

def execute():
    for item in FIELDS:
        fieldname,fieldtype,label=item[:3]
        options=item[3] if len(item)>3 else None
        select_options=item[4] if len(item)>4 else None
        _custom_field("Communication Event",fieldname,fieldtype,label,options,select_options)
    _page("communication-center","Communication Center")
    _page("ai-insights-dashboard","AI Insights Dashboard")
    frappe.clear_cache()

def _custom_field(dt,fieldname,fieldtype,label,options=None,select_options=None):
    if fieldtype=="Link" and options and not frappe.db.exists("DocType",options):
        return
    name=f"{dt}-{fieldname}"
    if frappe.db.exists("Custom Field",name):
        return
    doc=frappe.get_doc({"doctype":"Custom Field","dt":dt,"fieldname":fieldname,"label":label,"fieldtype":fieldtype,"insert_after":"content","options":select_options or options})
    try:
        doc.insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        return

def _page(name,title):
    if frappe.db.exists("Page",name):
        return
    doc=frappe.get_doc({"doctype":"Page","page_name":name,"module":"Visa CRM","title":title,"standard":"Yes"})
    try:
        doc.insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        return
