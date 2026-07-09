import frappe

@frappe.whitelist()
def receive(payload):
    if frappe.session.user=="Guest" or "System Manager" not in frappe.get_roles():
        frappe.throw("System Manager role required", frappe.PermissionError)
    queue=frappe.get_doc({
    "doctype":"Lead Intake Queue",
    "lead_source":"WhatsApp",
    "raw_payload":payload,
    "status":"Received"
    })
    queue.insert(ignore_permissions=True)
    frappe.db.commit()
    return{"success":True}
