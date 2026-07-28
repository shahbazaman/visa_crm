import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
    _fields()
    _pages()
    _workspace()
    frappe.db.commit()

def _fields():
    if frappe.db.exists("DocType", "Meta Webhook Event"):
        create_custom_fields({"Meta Webhook Event": [
            {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer", "insert_after": "crm_lead"},
            {"fieldname": "visa_application", "label": "Visa Application", "fieldtype": "Link", "options": "Visa Application", "insert_after": "customer"},
            {"fieldname": "communication_event", "label": "Communication Event", "fieldtype": "Link", "options": "Communication Event", "insert_after": "visa_application"}
        ]}, update=True)

def _pages():
    for name, title in {"meta-tools": "Meta Tools", "intake-pipeline": "Lead Intake Pipeline", "meta-live-monitor": "Meta Live Monitor"}.items():
        if not frappe.db.exists("Page", name):
            frappe.get_doc({"doctype": "Page", "page_name": name, "title": title, "module": "Visa CRM", "standard": "Yes"}).insert(ignore_permissions=True)

def _workspace():
    if not frappe.db.exists("Workspace", "Visa CRM"):
        return
    doc = frappe.get_doc("Workspace", "Visa CRM")
    links = [
        ("Production Health", "Page", "production-health"),
        ("Meta Live Monitor", "Page", "meta-live-monitor"),
        ("Lead Intake Pipeline", "Page", "intake-pipeline"),
        ("Queue Diagnostics", "Page", "lead-queue-diagnostics"),
        ("Scheduler Diagnostics", "Page", "scheduler-diagnostics"),
        ("Production Tools", "Page", "production-tools"),
        ("Meta Tools", "Page", "meta-tools")
    ]
    existing = {(row.get("label"), row.get("link_to")) for row in doc.get("shortcuts", [])}
    for label, link_type, link_to in links:
        if (label, link_to) not in existing:
            doc.append("shortcuts", {"type": link_type, "label": label, "link_to": link_to})
    doc.save(ignore_permissions=True)
