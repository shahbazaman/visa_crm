import frappe

def create_communication_event(call_doc):
    existing=frappe.db.exists("Communication Event",{"call_intelligence":call_doc.name})
    if existing:
        from visa_crm.api.customer360 import link_customer
        link_customer(call_doc)
        return existing
    communication=frappe.get_doc({
        "doctype":"Communication Event",
        "call_intelligence":call_doc.name,
        "source":"Phone",
        "event_type":"Call",
        "direction":"Inbound",
        "phone":call_doc.customer_phone_extracted,
        "summary":call_doc.summary,
        "content":call_doc.transcription,
        "sentiment":call_doc.emotion,
        "lead_score":call_doc.lead_score,
        "event_datetime":call_doc.creation,
        "recording_file":call_doc.recording_file
    })
    communication.insert(ignore_permissions=True)
    from visa_crm.api.customer360 import link_customer
    link_customer(call_doc)
    frappe.db.commit()
    return communication.name