import importlib
import os
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

LOG=[]
STAGES="New\nAssigned\nContacted\nInterested\nDocuments Pending\nDocuments Received\nUnder Verification\nVisa Processing\nSubmitted\nApproved\nRejected\nCancelled\nLost"
FIELDS={
    "CRM Lead":[("country","Data",None,"Country"),("visa_type","Data",None,"Visa Type"),("customer360","Link","Customer","Customer360"),("customer_360","Link","Customer","Customer360"),("customer_360_match","Link","Customer","Customer360 Match"),("assigned_counselor","Link","Employee","Assigned Counselor"),("assigned_employee","Link","Employee","Assigned Employee"),("timeline","Long Text",None,"Timeline"),("lead_timeline","Link","Lead Timeline","Lead Timeline"),("communication_history","Long Text",None,"Communication History"),("communication_events","Long Text",None,"Communication Events"),("visa_applications","Long Text",None,"Visa Applications"),("visa_application","Link","Visa Application","Visa Application"),("documents","Long Text",None,"Documents"),("customer_documents","Link","Customer Documents","Customer Documents"),("payments","Long Text",None,"Payments"),("payment_schedule","Link","Payment Schedule","Payment Schedule"),("workflow_stage","Select",STAGES,"Workflow Stage")],
    "Communication Event":[("ai_next_best_action","Long Text",None,"AI Next Best Action"),("ai_customer_priority","Int",None,"AI Customer Priority"),("conversation_status","Select","Open\nPending\nResolved\nArchived","Conversation Status"),("assigned_user","Link","User","Assigned User"),("assigned_counselor","Link","Employee","Assigned Counselor"),("visa_application","Link","Visa Application","Visa Application"),("communication_history","Long Text",None,"Communication History")],
    "Visa Application":[("lead","Link","CRM Lead","Lead"),("customer","Link","Customer","Customer"),("country","Data",None,"Country"),("visa_type","Data",None,"Visa Type"),("assigned_counselor","Link","Employee","Assigned Counselor"),("timeline","Long Text",None,"Timeline"),("communication_history","Long Text",None,"Communication History"),("documents","Long Text",None,"Documents"),("payments","Long Text",None,"Payments")],
    "Lead Intake Queue":[("retry_count","Int",None,"Retry Count"),("last_error","Small Text",None,"Last Error"),("next_retry_at","Datetime",None,"Next Retry At"),("processing_started_at","Datetime",None,"Processing Started At"),("processing_completed_at","Datetime",None,"Processing Completed At"),("communication_event","Link","Communication Event","Communication Event"),("matched_customer","Link","Customer","Matched Customer"),("matched_lead","Link","CRM Lead","Matched Lead")],
    "Customer":[("customer360","Long Text",None,"Customer360"),("assigned_counselor","Link","Employee","Assigned Counselor"),("timeline","Long Text",None,"Timeline"),("communication_history","Long Text",None,"Communication History"),("visa_applications","Long Text",None,"Visa Applications"),("documents","Long Text",None,"Documents"),("payments","Long Text",None,"Payments")],
    "Payment Schedule":[("lead","Link","CRM Lead","Lead"),("customer","Link","Customer","Customer"),("visa_application","Link","Visa Application","Visa Application"),("assigned_counselor","Link","Employee","Assigned Counselor")],
    "Customer Documents":[("lead","Link","CRM Lead","Lead"),("customer","Link","Customer","Customer"),("visa_application","Link","Visa Application","Visa Application"),("assigned_counselor","Link","Employee","Assigned Counselor"),("document_file","Attach",None,"Document File"),("verification_status","Select","Pending\nVerified\nRejected","Verification Status")]
}
REPORTS={"Lead Conversion":("CRM Lead","select count(*) leads from `tabCRM Lead`"),"Revenue":("Payment Schedule","select count(*) rows_count from `tabPayment Schedule`"),"Employee Performance":("Lead Assignment","select count(*) rows_count from `tabLead Assignment`"),"Source Performance":("CRM Lead","select count(*) leads from `tabCRM Lead`"),"Visa Processing":("Visa Application","select count(*) applications from `tabVisa Application`"),"Visa Processing Performance":("Visa Application","select count(*) applications from `tabVisa Application`"),"Pending Documents":("Customer Documents","select count(*) documents from `tabCustomer Documents`"),"Lost Lead Analysis":("CRM Lead","select count(*) leads from `tabCRM Lead`")}
PRINTS={"Visa Application":("Visa Application","<h2>Visa Application</h2><table class=\"table table-bordered\"><tr><th>Application</th><td>{{ doc.name }}</td></tr><tr><th>Applicant</th><td>{{ doc.get('applicant_name') or doc.get('customer') or '' }}</td></tr><tr><th>Visa Type</th><td>{{ doc.get('visa_type') or '' }}</td></tr><tr><th>Country</th><td>{{ doc.get('country') or doc.get('country_interested') or '' }}</td></tr><tr><th>Status</th><td>{{ doc.get('status') or doc.get('workflow_stage') or '' }}</td></tr></table>"),"Payment Receipt":("Payment Schedule","<h2>Payment Receipt</h2><table class=\"table table-bordered\"><tr><th>Receipt</th><td>{{ doc.name }}</td></tr><tr><th>Lead</th><td>{{ doc.get('lead') or '' }}</td></tr><tr><th>Amount</th><td>{% if doc.meta.has_field('amount') %}{{ doc.get_formatted('amount') }}{% endif %}</td></tr><tr><th>Status</th><td>{{ doc.get('status') or doc.get('payment_status') or '' }}</td></tr></table>"),"Customer Profile":("Customer","<h2>Customer Profile</h2><table class=\"table table-bordered\"><tr><th>Customer</th><td>{{ doc.get('customer_name') or doc.name }}</td></tr><tr><th>Phone</th><td>{{ doc.get('mobile_no') or doc.get('phone') or doc.get('whatsapp_no') or '' }}</td></tr><tr><th>Email</th><td>{{ doc.get('email_id') or doc.get('email') or '' }}</td></tr></table>"),"Document Checklist":("Customer Documents","<h2>Document Checklist</h2><table class=\"table table-bordered\"><tr><th>Record</th><td>{{ doc.name }}</td></tr><tr><th>Lead</th><td>{{ doc.get('lead') or '' }}</td></tr><tr><th>Document</th><td>{{ doc.get('document_type') or doc.get('document_name') or '' }}</td></tr><tr><th>Status</th><td>{{ doc.get('status') or doc.get('verification_status') or '' }}</td></tr></table>")}
PAGES={"communication-center":"Communication Center","ai-insights-dashboard":"AI Insights Dashboard"}
CARDS=[("New Leads","CRM Lead"),("Active Leads","CRM Lead"),("Pending Documents","Customer Documents"),("Visa Processing","Visa Application"),("Approved Visas","Visa Application"),("Overdue Follow-ups","ToDo")]
CHARTS=[("Visa Lead Stage Mix","CRM Lead"),("Visa Source Performance","CRM Lead"),("Visa Application Pipeline","Visa Application"),("Document Verification Status","Customer Documents"),("Payment Collection Status","Payment Schedule")]
ENDPOINTS=("visa_crm.api.communication_center.shared_inbox","visa_crm.api.communication_center.get_inbox","visa_crm.api.communication_center.conversation","visa_crm.api.ai_intelligence.insights_dashboard","visa_crm.www.visa_portal.portal_summary","visa_crm.www.document_upload.register_document")

def execute():
    for fn in (_fields,_pages,_reports,_prints,_cards,_charts,_dashboards,_workspace,_website_routes,_endpoints):
        _safe(fn)
    frappe.clear_cache()
    frappe.logger("visa_crm.migration").info("Visa CRM stabilization verification "+frappe.as_json(LOG))

def _fields():
    for dt, specs in FIELDS.items():
        if not _exists("DocType",dt):
            _log("missing_doctype",dt); continue
        meta=frappe.get_meta(dt)
        rows=[]
        for fieldname, fieldtype, options, label in specs:
            if meta.has_field(fieldname) or (fieldtype=="Link" and options and not _exists("DocType",options)):
                continue
            rows.append({"fieldname":fieldname,"label":label,"fieldtype":fieldtype,"options":options,"insert_after":_insert_after(meta)})
        if rows:
            create_custom_fields({dt:rows},update=True)
            _log("fields_created",dt,len(rows))

def _pages():
    for name,title in PAGES.items():
        if not _exists("Page",name):
            _insert({"doctype":"Page","page_name":name,"title":title,"module":"Visa CRM","standard":"Yes"},"Page",name)

def _reports():
    for name,(dt,query) in REPORTS.items():
        if not _exists("DocType",dt):
            _log("report_skip_doctype",name,dt); continue
        if _exists("Report",name):
            doc=frappe.get_doc("Report",name)
            _set(doc,{"ref_doctype":dt,"report_type":"Query Report","is_standard":"No","module":"Visa CRM","query":query})
            _save(doc,"Report",name); continue
        _insert({"doctype":"Report","report_name":name,"ref_doctype":dt,"report_type":"Query Report","is_standard":"No","module":"Visa CRM","query":query},"Report",name)

def _prints():
    for name,(dt,html) in PRINTS.items():
        if _exists("DocType",dt) and not _exists("Print Format",name):
            _insert({"doctype":"Print Format","name":name,"doc_type":dt,"module":"Visa CRM","standard":"No","custom_format":1,"print_format_type":"Jinja","html":html},"Print Format",name)

def _cards():
    if not _exists("DocType","Number Card"):
        return
    for name,dt in CARDS:
        if not _exists("DocType",dt) or _exists("Number Card",name):
            continue
        doc=frappe.new_doc("Number Card")
        _set(doc,{"label":name,"document_type":dt,"function":"Count","is_public":1,"module":"Visa CRM"})
        _save(doc,"Number Card",name)

def _charts():
    if not _exists("DocType","Dashboard Chart"):
        return
    for name,dt in CHARTS:
        if not _exists("DocType",dt) or _exists("Dashboard Chart",name):
            continue
        doc=frappe.new_doc("Dashboard Chart")
        _set(doc,{"chart_name":name,"document_type":dt,"chart_type":"Donut","type":"Count","is_public":1,"module":"Visa CRM","timeseries":0,"is_timeseries":0,"based_on":"creation","timespan":"Last Year","time_interval":"Monthly"})
        _save(doc,"Dashboard Chart",name)

def _dashboards():
    if not _exists("DocType","Dashboard"):
        return
    chart=next((name for name,_dt in CHARTS if _exists("Dashboard Chart",name)),None)
    for name in ("Sales Dashboard","Counselor Dashboard","Visa Processing Dashboard","Management Dashboard","Follow-up Dashboard","AI Manager Dashboard"):
        if _exists("Dashboard",name) or not chart:
            continue
        doc=frappe.new_doc("Dashboard")
        _set(doc,{"dashboard_name":name,"module":"Visa CRM"})
        if doc.meta.has_field("charts"):
            doc.append("charts",{"chart":chart,"width":"Half"})
        _save(doc,"Dashboard",name)

def _workspace():
    if not _exists("DocType","Workspace"):
        return
    links=[("Lead Intake Queue","DocType","Lead Intake Queue"),("CRM Lead","DocType","CRM Lead"),("Customer","DocType","Customer"),("Communication Center","Page","communication-center"),("AI Insights Dashboard","Page","ai-insights-dashboard"),("Visa Application","DocType","Visa Application"),("Reports","Report","Lead Conversion"),("Dashboard","Dashboard","Sales Dashboard")]
    shortcuts=[]; content=[{"id":"visa-header","type":"header","data":{"text":"<span class=\"h4\"><b>Visa CRM</b></span>","col":12}}]
    for i,(label,typ,link) in enumerate(links):
        if not _target(typ,link):
            _log("workspace_skip",label,typ,link); continue
        content.append({"id":f"visa-{i}","type":"shortcut","data":{"shortcut_name":label,"col":3}})
        shortcuts.append({"label":label,"type":typ,"link_to":link,"link_type":typ})
    doc=frappe.get_doc("Workspace","Visa CRM") if _exists("Workspace","Visa CRM") else frappe.new_doc("Workspace")
    _set(doc,{"name":"Visa CRM","label":"Visa CRM","title":"Visa CRM","module":"Visa CRM","public":1,"content":frappe.as_json(content)})
    if doc.meta.has_field("shortcuts"):
        doc.set("shortcuts",shortcuts)
    _save(doc,"Workspace","Visa CRM")

def _website_routes():
    for path in ("visa_portal.py","visa_portal.html","document_upload.py","document_upload.html"):
        full=frappe.get_app_path("visa_crm","www",path)
        if not os.path.exists(full):
            _log("route_missing",path)

def _endpoints():
    for path in ENDPOINTS:
        module,name=path.rsplit(".",1)
        obj=getattr(importlib.import_module(module),name,None)
        if not callable(obj):
            _log("endpoint_missing",path)
        elif not getattr(obj,"whitelisted",None):
            _log("endpoint_not_whitelisted",path)

def _target(typ,link):
    return _exists({"DocType":"DocType","Page":"Page","Report":"Report","Dashboard":"Dashboard"}.get(typ,typ),link)

def _insert_after(meta):
    for field in ("status","content","customer","lead","remarks"):
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
        if getattr(doc,"name",None) and _exists(doctype,doc.name):
            doc.save(ignore_permissions=True)
        else:
            doc.insert(ignore_permissions=True,ignore_if_duplicate=True)
        _log("ensured",doctype,name)
    except Exception:
        _log("skip",doctype,name,frappe.get_traceback())

def _safe(fn):
    try:
        fn()
    except Exception:
        _log("safe_skip",fn.__name__,frappe.get_traceback())

def _exists(doctype,name):
    return bool(frappe.db.exists(doctype,name))

def _log(action,*values):
    LOG.append({"action":action,"values":values})
