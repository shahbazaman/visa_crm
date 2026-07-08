import frappe

ROLES = ["Administrator", "Sales Manager", "Counselor", "Visa Processing", "Ticket Team", "Digital Marketer", "Read-only Auditor"]
STAGES = "New\nAssigned\nContacted\nInterested\nDocuments Pending\nDocuments Received\nUnder Verification\nVisa Processing\nSubmitted\nApproved\nRejected\nCancelled\nLost"
SHORTCUTS = [("CRM Lead", "DocType", "CRM Lead"), ("Customer", "DocType", "Customer"), ("Visa Application", "DocType", "Visa Application"), ("Customer Documents", "DocType", "Customer Documents"), ("Payment Schedule", "DocType", "Payment Schedule"), ("ToDo", "DocType", "ToDo"), ("Communication Event", "DocType", "Communication Event"), ("Notification Log", "DocType", "Notification Log"), ("Communication Center", "Page", "communication-center"), ("AI Insights Dashboard", "Page", "ai-insights-dashboard"), ("Lead Conversion", "Report", "Lead Conversion"), ("Visa Processing Performance", "Report", "Visa Processing Performance"), ("Follow-up Dashboard", "Dashboard", "Follow-up Dashboard"), ("Management Dashboard", "Dashboard", "Management Dashboard")]
REPORTS = {"Lead Conversion": ("CRM Lead", "select status,count(*) leads from `tabCRM Lead` group by status"), "Visa Processing Performance": ("Visa Application", "select status,count(*) applications from `tabVisa Application` group by status"), "Employee Performance": ("Lead Assignment", "select assigned_to,count(*) assigned from `tabLead Assignment` group by assigned_to"), "Revenue": ("Payment Schedule", "select status,sum(amount) amount from `tabPayment Schedule` group by status"), "Source Performance": ("CRM Lead", "select source,count(*) leads from `tabCRM Lead` group by source"), "Pending Documents": ("Customer Documents", "select lead,document_type,status from `tabCustomer Documents` where status!='Verified'"), "Lost Lead Analysis": ("CRM Lead", "select status,count(*) leads from `tabCRM Lead` where status in ('Lost','Rejected','Cancelled') group by status")}
PRINTS = {"Visa Application": ("Visa Application", "<h2>Visa Application</h2><p><b>ID:</b> {{ doc.name }}</p><p><b>Applicant:</b> {{ doc.applicant_name }}</p><p><b>Visa:</b> {{ doc.visa_type }} - {{ doc.country }}</p><p><b>Status:</b> {{ doc.status }}</p>"), "Customer Profile": ("Customer", "<h2>Customer Profile</h2><p><b>Name:</b> {{ doc.customer_name }}</p><p><b>Phone:</b> {{ doc.mobile_no or doc.phone }}</p><p><b>Email:</b> {{ doc.email_id }}</p>"), "Payment Receipt": ("Payment Schedule", "<h2>Payment Receipt</h2><p><b>Lead:</b> {{ doc.lead }}</p><p><b>Amount:</b> {{ doc.get_formatted('amount') }}</p><p><b>Status:</b> {{ doc.status }}</p>"), "Document Checklist": ("Customer Documents", "<h2>Document Checklist</h2><p><b>Lead:</b> {{ doc.lead }}</p><p><b>Document:</b> {{ doc.document_type }}</p><p><b>Status:</b> {{ doc.status }}</p>")}
CHARTS = [("Visa Lead Stage Mix", "CRM Lead", "status"), ("Visa Source Performance", "CRM Lead", "source"), ("Visa Application Pipeline", "Visa Application", "status"), ("Document Verification Status", "Customer Documents", "status"), ("Payment Collection Status", "Payment Schedule", "status")]
CARDS = [("New Leads", "CRM Lead", {"status": "New"}), ("Active Leads", "CRM Lead", {}), ("Pending Documents", "Customer Documents", {"status": "Pending"}), ("Visa Processing", "Visa Application", {"status": "Visa Processing"}), ("Approved Visas", "Visa Application", {"status": "Approved"}), ("Overdue Follow-ups", "ToDo", {"status": "Open"})]

def execute():
    for fn in (_roles, _reports, _print_formats, _charts, _cards, _dashboards, _workspace, _kanban, _permissions):
        _safe(fn)

def _roles():
    for role in ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)

def _reports():
    for name, (ref, query) in REPORTS.items():
        if frappe.db.exists("DocType", ref) and not frappe.db.exists("Report", name):
            try:
                frappe.get_doc({"doctype": "Report", "report_name": name, "ref_doctype": ref, "report_type": "Query Report", "is_standard": "No", "module": "Visa CRM", "query": query}).insert(ignore_permissions=True)
            except Exception:
                frappe.logger("visa_crm.migration").warning(f"Skipped Report {name}: {frappe.get_traceback()}")

def _print_formats():
    for name, (dt, html) in PRINTS.items():
        if frappe.db.exists("DocType", dt) and not frappe.db.exists("Print Format", name):
            try:
                frappe.get_doc({"doctype": "Print Format", "name": name, "doc_type": dt, "module": "Visa CRM", "standard": "No", "custom_format": 1, "print_format_type": "Jinja", "html": html}).insert(ignore_permissions=True)
            except Exception:
                frappe.logger("visa_crm.migration").warning(f"Skipped Print Format {name}: {frappe.get_traceback()}")

def _dashboards():
    for name in ("Sales Dashboard", "Counselor Dashboard", "Visa Processing Dashboard", "Management Dashboard", "Follow-up Dashboard"):
        if frappe.db.exists("Dashboard", name):
            continue
        doc = frappe.new_doc("Dashboard")
        doc.dashboard_name = name
        doc.module = "Visa CRM"
        try:
            doc.insert(ignore_permissions=True)
        except Exception:
            frappe.logger("visa_crm.migration").warning(f"Skipped Dashboard {name}: {frappe.get_traceback()}")

def _charts():
    if not frappe.db.exists("DocType", "Dashboard Chart"):
        return
    for name, doctype, group_by in CHARTS:
        if not frappe.db.exists("DocType", doctype) or frappe.db.exists("Dashboard Chart", name):
            continue
        doc = frappe.new_doc("Dashboard Chart")
        for field, value in {"chart_name": name, "chart_type": "Donut", "document_type": doctype, "group_by_type": "Count", "group_by_based_on": group_by, "is_public": 1, "timeseries": 0, "is_timeseries": 0, "based_on": "creation", "timespan": "Last Year", "time_interval": "Monthly", "number_of_groups": 10, "type": "Group By"}.items():
            if doc.meta.has_field(field):
                doc.set(field, value)
        try:
            doc.insert(ignore_permissions=True)
        except Exception:
            frappe.logger("visa_crm.migration").warning(f"Skipped Dashboard Chart {name}: {frappe.get_traceback()}")

def _cards():
    if not frappe.db.exists("DocType", "Number Card"):
        return
    for name, doctype, filters in CARDS:
        if not frappe.db.exists("DocType", doctype) or frappe.db.exists("Number Card", name):
            continue
        doc = frappe.new_doc("Number Card")
        for field, value in {"label": name, "document_type": doctype, "function": "Count", "is_public": 1, "filters_json": frappe.as_json(filters)}.items():
            if doc.meta.has_field(field):
                doc.set(field, value)
        try:
            doc.insert(ignore_permissions=True)
        except Exception:
            frappe.logger("visa_crm.migration").warning(f"Skipped Number Card {name}: {frappe.get_traceback()}")

def _workspace():
    existing = frappe.db.exists("Workspace", "Visa CRM")
    content = [{"id": "visa-header", "type": "header", "data": {"text": "<span class=\"h4\"><b>Visa CRM Operations</b></span>", "col": 12}}]
    shortcuts = []
    for idx, (label, link_type, link_to) in enumerate(SHORTCUTS):
        if not _target_exists(link_type, link_to):
            continue
        content.append({"id": f"visa-{idx}", "type": "shortcut", "data": {"shortcut_name": label, "col": 3}})
        shortcuts.append({"label": label, "type": link_type, "link_to": link_to, "link_type": link_type})
    if existing:
        doc = frappe.get_doc("Workspace", "Visa CRM")
        doc.content = frappe.as_json(content)
        doc.set("shortcuts", shortcuts)
        try:
            doc.save(ignore_permissions=True)
        except Exception:
            frappe.logger("visa_crm.migration").warning(f"Skipped Workspace repair: {frappe.get_traceback()}")
        return
    try:
        frappe.get_doc({"doctype": "Workspace", "name": "Visa CRM", "label": "Visa CRM", "title": "Visa CRM", "module": "Visa CRM", "public": 1, "content": frappe.as_json(content), "shortcuts": shortcuts}).insert(ignore_permissions=True)
    except Exception:
        frappe.logger("visa_crm.migration").warning(f"Skipped Workspace create: {frappe.get_traceback()}")

def _kanban():
    if not frappe.db.exists("DocType", "Kanban Board") or frappe.db.exists("Kanban Board", "CRM Lead by Stage"):
        return
    doc = frappe.new_doc("Kanban Board")
    doc.kanban_board_name = "CRM Lead by Stage"
    doc.reference_doctype = "CRM Lead"
    doc.field_name = _stage_field()
    try:
        doc.insert(ignore_permissions=True)
    except Exception:
        frappe.logger("visa_crm.migration").warning(f"Skipped Kanban Board CRM Lead by Stage: {frappe.get_traceback()}")

def _permissions():
    doctypes = ["CRM Lead", "Visa Application", "Customer Documents", "Follow-up History", "Counselor Assignment History", "Lead Timeline", "Activity Log", "Payment Schedule", "Visa Status Log", "Communication Event"]
    for doctype in doctypes:
        if not frappe.db.exists("DocType", doctype):
            continue
        for role in ROLES:
            _permission(doctype, role, read=1, write=0 if role == "Read-only Auditor" else 1, create=0 if role == "Read-only Auditor" else 1)

def _permission(doctype, role, read=1, write=1, create=1):
    if frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role}):
        return
    try:
        frappe.get_doc({"doctype": "Custom DocPerm", "parent": doctype, "parenttype": "DocType", "parentfield": "permissions", "role": role, "read": read, "write": write, "create": create, "export": read, "print": read, "report": read}).insert(ignore_permissions=True)
    except Exception:
        frappe.logger("visa_crm.migration").warning(f"Skipped permission {doctype} {role}: {frappe.get_traceback()}")

def _stage_field():
    meta = frappe.get_meta("CRM Lead")
    for field in ("workflow_stage", "workflow_state", "stage", "status"):
        if meta.has_field(field):
            return field
    return "status"

def _target_exists(link_type, link_to):
    checks = {"DocType": "DocType", "Report": "Report", "Dashboard": "Dashboard", "Page": "Page"}
    return frappe.db.exists(checks.get(link_type, link_type), link_to)

def _safe(fn):
    try:
        fn()
    except Exception:
        frappe.logger("visa_crm.migration").warning(f"Skipped {fn.__name__}: {frappe.get_traceback()}")
