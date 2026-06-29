import frappe

@frappe.whitelist()
def receive(payload):
    queue=frappe.get_doc({
    "doctype":"Lead Intake Queue",
    "lead_source":"WhatsApp",
    "raw_payload":payload,
    "status":"Received"
    })
    queue.insert(ignore_permissions=True)
    frappe.db.commit()
    return{"success":True}