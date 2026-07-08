import frappe

SOURCES = ["Manual", "Meta Instant Form", "Website", "WhatsApp"]

def execute():
    _sources()
    _demo_leads()

def _sources():
    for doctype in ("Source", "CRM Lead Source"):
        if not frappe.db.exists("DocType", doctype):
            continue
        for source in SOURCES:
            if frappe.db.exists(doctype, source):
                continue
            doc = frappe.new_doc(doctype)
            doc.name = source
            for field in (doc.meta.title_field, "source_name", "lead_source", "source", "title"):
                if field and doc.meta.has_field(field):
                    doc.set(field, source)
                    break
            doc.insert(ignore_permissions=True, ignore_if_duplicate=True)

def _demo_leads():
    if not frappe.db.exists("DocType", "CRM Lead") or frappe.db.count("CRM Lead") > 0:
        return
    from visa_crm.api.lead_creator import create_crm_lead
    rows = [{"customer_name": "Demo Student Lead", "phone": "+971500000001", "email": "student@example.com", "visa_type": "Student", "country_interested": "Canada", "source": "Manual", "stage": "Approved"}, {"customer_name": "Demo Work Lead", "phone": "+971500000002", "email": "work@example.com", "visa_type": "Work", "country_interested": "UAE", "source": "Website", "stage": "Visa Processing"}, {"customer_name": "Demo Visit Lead", "phone": "+971500000003", "email": "visit@example.com", "visa_type": "Visit", "country_interested": "Schengen", "source": "WhatsApp", "stage": "Documents Pending"}]
    for row in rows:
        lead = create_crm_lead(row)
        _stage(lead, row["stage"])
        _application(lead, row)
        _documents(lead, row)
        _payments(lead, row)
        _logs(lead, row["stage"])

def _stage(lead, stage):
    doc = frappe.get_doc("CRM Lead", lead)
    for field in ("workflow_stage", "workflow_state", "stage", "status"):
        if doc.meta.has_field(field):
            doc.set(field, stage)
            break
    doc.save(ignore_permissions=True)

def _application(lead, row):
    if not frappe.db.exists("DocType", "Visa Application") or frappe.db.exists("Visa Application", {"lead": lead}):
        return
    doc = frappe.new_doc("Visa Application")
    for field, value in {"lead": lead, "applicant_name": row["customer_name"], "visa_type": row["visa_type"], "country": row["country_interested"], "status": "Approved" if row["stage"] == "Approved" else row["stage"]}.items():
        if doc.meta.has_field(field):
            doc.set(field, value)
    doc.insert(ignore_permissions=True)

def _documents(lead, row):
    if not frappe.db.exists("DocType", "Customer Documents"):
        return
    for name in ("Passport", "Photo", "Bank Statement"):
        if frappe.db.exists("Customer Documents", {"lead": lead, "document_type": name}):
            continue
        doc = frappe.new_doc("Customer Documents")
        for field, value in {"lead": lead, "document_type": name, "status": "Verified" if row["stage"] == "Approved" else "Pending", "visa_type": row["visa_type"], "country": row["country_interested"]}.items():
            if doc.meta.has_field(field):
                doc.set(field, value)
        doc.insert(ignore_permissions=True)

def _payments(lead, row):
    if not frappe.db.exists("DocType", "Payment Schedule") or frappe.db.exists("Payment Schedule", {"lead": lead}):
        return
    doc = frappe.new_doc("Payment Schedule")
    for field, value in {"lead": lead, "amount": 2500, "due_date": frappe.utils.today(), "status": "Paid" if row["stage"] == "Approved" else "Pending"}.items():
        if doc.meta.has_field(field):
            doc.set(field, value)
    doc.insert(ignore_permissions=True)

def _logs(lead, stage):
    if not frappe.db.exists("DocType", "Visa Status Log"):
        return
    for target in ("New", "Assigned", "Contacted", "Interested", "Documents Pending", "Documents Received", "Under Verification", "Visa Processing", "Submitted", stage):
        if frappe.db.exists("Visa Status Log", {"lead": lead, "to_stage": target}):
            continue
        doc = frappe.new_doc("Visa Status Log")
        for field, value in {"lead": lead, "to_stage": target, "changed_by": "Administrator", "changed_on": frappe.utils.now()}.items():
            if doc.meta.has_field(field):
                doc.set(field, value)
        doc.insert(ignore_permissions=True)
        if target == stage:
            break
