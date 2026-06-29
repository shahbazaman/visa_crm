import frappe

def update_customer_profile(doc):
    if not doc.customer_360_match:
        return
    customer=frappe.get_doc("Customer",doc.customer_360_match)
    customer.last_contacted=frappe.utils.now()
    customer.last_summary=doc.summary
    customer.last_sentiment=doc.emotion
    customer.last_lead_score=doc.lead_score
    customer.current_counselor=doc.employee_match
    customer.last_visa_interest=doc.country_of_interest
    customer.communication_count=frappe.db.count("Communication Event",{"customer":customer.name})
    customer.save(ignore_permissions=True)
    frappe.db.commit()

def link_customer(call_doc):
    if call_doc.customer_360_match:
        return
    customer=None
    if call_doc.customer_phone_extracted:
        customer=frappe.db.get_value("Customer",{"mobile_no":call_doc.customer_phone_extracted})
    if not customer and call_doc.customer_name:
        customer=frappe.db.get_value("Customer",{"customer_name":call_doc.customer_name})
    if customer:
        call_doc.db_set("customer_360_match",customer,update_modified=False)
        if call_doc.communication_event:
            event=frappe.get_doc("Communication Event",call_doc.communication_event)
            event.customer=customer
            event.save(ignore_permissions=True)
        frappe.db.commit()    