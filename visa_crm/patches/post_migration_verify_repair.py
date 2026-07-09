import importlib
import os
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

LOG=[]
STAGES="New\nAssigned\nContacted\nInterested\nDocuments Pending\nDocuments Received\nUnder Verification\nVisa Processing\nSubmitted\nApproved\nRejected\nCancelled\nLost"
CUSTOM_FIELDS={
    "Communication Event":[
        ("provider","Data",None),("provider_message_id","Data",None),("parent_conversation_id","Data",None),("assigned_user","Link","User"),("assigned_counselor","Link","Employee"),("conversation_status","Select","Open\nPending\nResolved\nArchived"),("unread","Check",None),("label","Data",None),("internal_notes","Long Text",None),("attachments","Long Text",None),("raw_channel_payload","Long Text",None),("deal","Link","CRM Deal"),("visa_application","Link","Visa Application"),("payment_schedule","Link","Payment Schedule"),("customer_documents","Link","Customer Documents"),("lead_timeline","Link","Lead Timeline"),("communication_history","Long Text",None),("country","Data",None),("visa_type","Data",None),("ai_next_best_action","Long Text",None),("ai_followup_suggestion","Long Text",None),("ai_lost_lead_analysis","Long Text",None),("ai_employee_coaching","Long Text",None),("ai_manager_summary","Long Text",None),("ai_reminder_suggestion","Long Text",None),("ai_customer_priority","Int",None),("ai_visa_recommendation","Long Text",None),("ai_quality_analysis","Long Text",None),("ai_timeline_summary","Long Text",None)
    ],
    "CRM Lead":[
        ("workflow_stage","Select",STAGES),("assigned_employee","Link","Employee"),("assigned_counselor","Link","Employee"),("visa_type","Data",None),("country_interested","Data",None),("country","Data",None),("customer_360","Link","Customer"),("customer_360_match","Link","Customer"),("visa_application","Link","Visa Application"),("lead_timeline","Link","Lead Timeline"),("communication_history","Long Text",None),("payment_schedule","Link","Payment Schedule"),("customer_documents","Link","Customer Documents"),("ai_next_best_action","Long Text",None),("ai_customer_priority","Int",None)
    ],
    "Customer":[
        ("whatsapp_no","Data",None),("assigned_counselor","Link","Employee"),("current_counselor","Link","Employee"),("customer_360_summary","Long Text",None),("communication_history","Long Text",None),("visa_application","Link","Visa Application"),("lead_timeline","Link","Lead Timeline"),("payment_schedule","Link","Payment Schedule"),("customer_documents","Link","Customer Documents"),("ai_customer_priority","Int",None),("ai_next_best_action","Long Text",None)
    ],
    "Visa Application":[
        ("lead","Link","CRM Lead"),("customer","Link","Customer"),("applicant_name","Data",None),("visa_type","Data",None),("country","Data",None),("country_interested","Data",None),("assigned_counselor","Link","Employee"),("workflow_stage","Select","Draft\nDocuments Pending\nUnder Verification\nVisa Processing\nSubmitted\nApproved\nRejected\nCancelled"),("progress","Percent",None),("communication_history","Long Text",None),("lead_timeline","Link","Lead Timeline"),("payment_schedule","Link","Payment Schedule"),("customer_documents","Link","Customer Documents")
    ],
    "Lead Intake Queue":[
        ("retry_count","Int",None),("last_error","Small Text",None),("next_retry_at","Datetime",None),("processing_started_at","Datetime",None),("processing_completed_at","Datetime",None),("graph_payload","Long Text",None),("custom_answers","Long Text",None),("page_id","Data",None),("form_id","Data",None),("campaign_id","Data",None),("adset_id","Data",None),("ad_id","Data",None),("communication_event","Link","Communication Event"),("followup_reference","Link","ToDo"),("customer_360_match","Link","Customer"),("matched_customer","Link","Customer"),("matched_lead","Link","CRM Lead"),("visa_application","Link","Visa Application")
    ],
    "Payment Schedule":[
        ("lead","Link","CRM Lead"),("customer","Link","Customer"),("visa_application","Link","Visa Application"),("assigned_counselor","Link","Employee"),("payment_status","Select","Pending\nPaid\nOverdue\nCancelled"),("receipt","Attach",None),("communication_history","Long Text",None)
    ],
    "Customer Documents":[
        ("lead","Link","CRM Lead"),("customer","Link","Customer"),("visa_application","Link","Visa Application"),("document_name","Data",None),("document_file","Attach",None),("verification_status","Select","Pending\nVerified\nRejected"),("expiry_date","Date",None),("assigned_counselor","Link","Employee"),("communication_history","Long Text",None)
    ],
    "Lead Timeline":[("customer","Link","Customer"),("communication_event","Link","Communication Event"),("visa_application","Link","Visa Application"),("title","Data",None),("note","Long Text",None)]
}
REPORTS={"Lead Conversion":("CRM Lead","select status,count(*) leads from `tabCRM Lead` group by status"),"Visa Processing Performance":("Visa Application","select status,count(*) applications from `tabVisa Application` group by status"),"Employee Performance":("Lead Assignment","select assigned_to,count(*) assigned from `tabLead Assignment` group by assigned_to"),"Revenue":("Payment Schedule","select status,sum(amount) amount from `tabPayment Schedule` group by status"),"Source Performance":("CRM Lead","select source,count(*) leads from `tabCRM Lead` group by source"),"Pending Documents":("Customer Documents","select lead,document_type,status from `tabCustomer Documents` where status!='Verified'"),"Lost Lead Analysis":("CRM Lead","select status,count(*) leads from `tabCRM Lead` where status in ('Lost','Rejected','Cancelled') group by status")}
PRINTS={"Visa Application":("Visa Application","<h2>Visa Application</h2><table class=\"table table-bordered\"><tr><th>Application</th><td>{{ doc.name }}</td></tr><tr><th>Applicant</th><td>{{ doc.get('applicant_name') or doc.get('customer') or '' }}</td></tr><tr><th>Visa Type</th><td>{{ doc.get('visa_type') or '' }}</td></tr><tr><th>Country</th><td>{{ doc.get('country') or doc.get('country_interested') or '' }}</td></tr><tr><th>Status</th><td>{{ doc.get('status') or doc.get('workflow_stage') or '' }}</td></tr></table>"),"Customer Profile":("Customer","<h2>Customer Profile</h2><table class=\"table table-bordered\"><tr><th>Customer</th><td>{{ doc.get('customer_name') or doc.name }}</td></tr><tr><th>Phone</th><td>{{ doc.get('mobile_no') or doc.get('phone') or doc.get('whatsapp_no') or '' }}</td></tr><tr><th>Email</th><td>{{ doc.get('email_id') or doc.get('email') or '' }}</td></tr></table>"),"Payment Receipt":("Payment Schedule","<h2>Payment Receipt</h2><table class=\"table table-bordered\"><tr><th>Receipt</th><td>{{ doc.name }}</td></tr><tr><th>Lead</th><td>{{ doc.get('lead') or '' }}</td></tr><tr><th>Amount</th><td>{% if doc.meta.has_field('amount') %}{{ doc.get_formatted('amount') }}{% endif %}</td></tr><tr><th>Status</th><td>{{ doc.get('status') or doc.get('payment_status') or '' }}</td></tr></table>"),"Document Checklist":("Customer Documents","<h2>Document Checklist</h2><table class=\"table table-bordered\"><tr><th>Record</th><td>{{ doc.name }}</td></tr><tr><th>Lead</th><td>{{ doc.get('lead') or '' }}</td></tr><tr><th>Document</th><td>{{ doc.get('document_type') or doc.get('document_name') or '' }}</td></tr><tr><th>Status</th><td>{{ doc.get('status') or doc.get('verification_status') or '' }}</td></tr></table>")}
CHARTS=[("Visa Lead Stage Mix","CRM Lead","status"),("Visa Source Performance","CRM Lead","source"),("Visa Application Pipeline","Visa Application","status"),("Document Verification Status","Customer Documents","status"),("Payment Collection Status","Payment Schedule","status")]
CARDS=[("New Leads","CRM Lead",{"status":"New"}),("Active Leads","CRM Lead",{}),("Pending Documents","Customer Documents",{"status":"Pending"}),("Visa Processing","Visa Application",{"status":"Visa Processing"}),("Approved Visas","Visa Application",{"status":"Approved"}),("Overdue Follow-ups","ToDo",{"status":"Open"})]
PAGES={"communication-center":"Communication Center","ai-insights-dashboard":"AI Insights Dashboard"}
ENDPOINTS=["visa_crm.api.communication_center.shared_inbox","visa_crm.api.communication_center.get_inbox","visa_crm.api.communication_center.get_shared_inbox","visa_crm.api.communication_center.conversation","visa_crm.api.communication_center.update_conversation","visa_crm.api.communication_center.receive_channel","visa_crm.api.communication_center.send_reply","visa_crm.api.ai_intelligence.insights_dashboard","visa_crm.api.mobile_api.inbox","visa_crm.api.mobile_api.get_inbox","visa_crm.www.document_upload.register_document","visa_crm.www.visa_portal.portal_summary"]

def execute():
    _custom_fields()
    _pages()
    _reports()
    _print_formats()
    _dashboards()
    _charts()
    _cards()
    _kanban()
    _workspace()
    _routes()
    _endpoints()
    frappe.clear_cache()
    frappe.logger("visa_crm.migration").info("Visa CRM post migration verification: "+frappe.as_json(LOG))

def _custom_fields():
    for dt, fields in CUSTOM_FIELDS.items():
        if not _exists("DocType", dt):
            _log("skip_doctype", dt)
            continue
        meta=frappe.get_meta(dt)
        rows=[]
        for fieldname, fieldtype, options in fields:
            if meta.has_field(fieldname) or (fieldtype=="Link" and options and not _exists("DocType", options)):
                continue
            rows.append({"fieldname":fieldname,"label":fieldname.replace("_"," ").title(),"fieldtype":fieldtype,"options":options,"insert_after":_insert_after(meta)})
        if rows:
            create_custom_fields({dt:rows}, update=True)
            _log("custom_fields", dt, len(rows))

def _pages():
    for name,title in PAGES.items():
        if _exists("Page", name):
            continue
        _insert({"doctype":"Page","page_name":name,"module":"Visa CRM","title":title,"standard":"Yes"},"Page",name)

def _reports():
    for name,(ref,query) in REPORTS.items():
        if not _exists("DocType", ref):
            continue
        if _exists("Report", name):
            doc=frappe.get_doc("Report", name)
            changed=False
            for field,value in {"ref_doctype":ref,"report_type":"Query Report","query":query}.items():
                if doc.meta.has_field(field) and doc.get(field)!=value:
                    doc.set(field,value); changed=True
            if changed:
                doc.save(ignore_permissions=True); _log("report_repaired", name)
            continue
        _insert({"doctype":"Report","report_name":name,"ref_doctype":ref,"report_type":"Query Report","is_standard":"No","query":query},"Report",name)

def _print_formats():
    for name,(dt,html) in PRINTS.items():
        if _exists("DocType", dt) and not _exists("Print Format", name):
            _insert({"doctype":"Print Format","name":name,"doc_type":dt,"module":"Visa CRM","standard":"No","custom_format":1,"print_format_type":"Jinja","html":html},"Print Format",name)

def _dashboards():
    if not _exists("DocType", "Dashboard"):
        return
    for name in ("Sales Dashboard","Counselor Dashboard","Visa Processing Dashboard","Management Dashboard","Follow-up Dashboard","AI Manager Dashboard"):
        if not _exists("Dashboard", name):
            _insert({"doctype":"Dashboard","dashboard_name":name,"module":"Visa CRM"},"Dashboard",name)

def _charts():
    if not _exists("DocType", "Dashboard Chart"):
        return
    for name,doctype,group_by in CHARTS:
        if _exists("DocType",doctype) and not _exists("Dashboard Chart",name):
            doc=frappe.new_doc("Dashboard Chart")
            _set(doc,{"chart_name":name,"chart_type":"Donut","document_type":doctype,"group_by_type":"Count","group_by_based_on":group_by,"is_public":1,"timeseries":0,"is_timeseries":0,"based_on":"creation","timespan":"Last Year","time_interval":"Monthly","number_of_groups":10,"type":"Group By"})
            try:
                _save(doc,"Dashboard Chart",name)
            except Exception:
                _log("chart_skip",name,frappe.get_traceback())

def _cards():
    if not _exists("DocType", "Number Card"):
        return
    for name,doctype,filters in CARDS:
        if _exists("DocType",doctype) and not _exists("Number Card",name):
            doc=frappe.new_doc("Number Card")
            _set(doc,{"label":name,"document_type":doctype,"function":"Count","is_public":1,"filters_json":frappe.as_json(filters)})
            _save(doc,"Number Card",name)

def _kanban():
    if _exists("DocType","Kanban Board") and _exists("DocType","CRM Lead") and not _exists("Kanban Board","CRM Lead by Stage"):
        doc=frappe.new_doc("Kanban Board")
        _set(doc,{"kanban_board_name":"CRM Lead by Stage","reference_doctype":"CRM Lead","field_name":_stage_field()})
        _save(doc,"Kanban Board","CRM Lead by Stage")

def _workspace():
    if not _exists("DocType","Workspace"):
        return
    shortcuts=[]
    content=[{"id":"visa-header","type":"header","data":{"text":"<span class=\"h4\"><b>Visa CRM Operations</b></span>","col":12}}]
    for idx,(label,typ,link) in enumerate(_workspace_links()):
        if not _target(typ,link):
            continue
        content.append({"id":f"visa-{idx}","type":"shortcut","data":{"shortcut_name":label,"col":3}})
        shortcuts.append({"label":label,"type":typ,"link_to":link,"link_type":typ})
    doc=frappe.get_doc("Workspace","Visa CRM") if _exists("Workspace","Visa CRM") else frappe.new_doc("Workspace")
    _set(doc,{"name":"Visa CRM","label":"Visa CRM","title":"Visa CRM","module":"Visa CRM","public":1,"content":frappe.as_json(content)})
    doc.set("shortcuts",shortcuts)
    _save(doc,"Workspace","Visa CRM")

def _routes():
    for route in ("visa_portal.py","visa_portal.html","document_upload.py","document_upload.html"):
        try:
            if not os.path.exists(frappe.get_app_path("visa_crm","www",route)):
                _log("missing_route_file", route)
        except Exception:
            _log("missing_route_file", route)

def _endpoints():
    for path in ENDPOINTS:
        module, name = path.rsplit(".",1)
        try:
            obj=getattr(importlib.import_module(module), name)
            if not callable(obj):
                _log("endpoint_not_callable", path)
        except Exception:
            _log("missing_endpoint", path)

def _workspace_links():
    return [("CRM Lead","DocType","CRM Lead"),("Customer","DocType","Customer"),("Visa Application","DocType","Visa Application"),("Customer Documents","DocType","Customer Documents"),("Payment Schedule","DocType","Payment Schedule"),("ToDo","DocType","ToDo"),("Communication Event","DocType","Communication Event"),("Communication Center","Page","communication-center"),("AI Insights Dashboard","Page","ai-insights-dashboard"),("Lead Conversion","Report","Lead Conversion"),("Visa Processing Performance","Report","Visa Processing Performance"),("Follow-up Dashboard","Dashboard","Follow-up Dashboard"),("Management Dashboard","Dashboard","Management Dashboard"),("AI Manager Dashboard","Dashboard","AI Manager Dashboard")]

def _target(typ,link):
    return _exists({"DocType":"DocType","Report":"Report","Dashboard":"Dashboard","Page":"Page"}.get(typ,typ), link)

def _stage_field():
    meta=frappe.get_meta("CRM Lead")
    for field in ("workflow_stage","workflow_state","stage","status"):
        if meta.has_field(field):
            return field
    return "status"

def _insert_after(meta):
    for field in ("content","status","customer","lead","remarks"):
        if meta.has_field(field):
            return field
    return None

def _set(doc,values):
    for field,value in values.items():
        if value is not None and (field=="name" or doc.meta.has_field(field)):
            doc.set(field,value)

def _insert(values,doctype,name):
    doc=frappe.get_doc(values)
    _save(doc,doctype,name)

def _save(doc,doctype,name):
    try:
        doc.save(ignore_permissions=True) if getattr(doc,"name",None) and _exists(doctype,doc.name) else doc.insert(ignore_permissions=True,ignore_if_duplicate=True)
        _log("ensured", doctype, name)
    except frappe.DuplicateEntryError:
        _log("duplicate_skip", doctype, name)
    except Exception:
        _log("save_skip", doctype, name, frappe.get_traceback())

def _exists(doctype,name):
    return bool(frappe.db.exists(doctype,name))

def _log(action,*values):
    LOG.append({"action":action,"values":values})
