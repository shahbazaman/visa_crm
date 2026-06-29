import frappe

def add_to_customer_timeline(customer,event):
    meta=frappe.get_meta("Customer")
    if not meta.has_field("communication_timeline"):
        return
    doc=frappe.get_doc("Customer",customer)
    doc.append("communication_timeline",{
        "communication_event":event.name,
        "event_datetime":event.event_datetime,
        "summary":event.summary,
        "employee":event.employee,
        "sentiment":event.sentiment,
        "call_intelligence":event.call_intelligence
    })
    doc.save(ignore_permissions=True)
    frappe.db.commit()