import frappe

def find_customer(phone=None,email=None,name=None):
    if phone:
        customer=frappe.db.get_value("Customer",{"mobile_no":phone},"name")
        if customer:
            return customer
        customer=frappe.db.get_value("Customer",{"phone":phone},"name")
        if customer:
            return customer
    if email:
        customer=frappe.db.get_value("Customer",{"email_id":email},"name")
        if customer:
            return customer
    if name:
        customer=frappe.db.get_value("Customer",{"customer_name":name},"name")
        if customer:
            return customer
    return None

def find_lead(phone=None,email=None):
    if phone:
        lead=frappe.db.get_value("CRM Lead",{"mobile_no":phone},"name")
        if lead:
            return lead
    if email:
        lead=frappe.db.get_value("CRM Lead",{"email":email},"name")
        if lead:
            return lead
    return None

def create_customer_from_lead(lead):
    doc=frappe.get_doc("CRM Lead",lead)
    customer=frappe.get_doc({
        "doctype":"Customer",
        "customer_name":doc.lead_name or doc.first_name or "Unknown",
        "mobile_no":doc.mobile_no,
        "email_id":doc.email
    })
    customer.insert(ignore_permissions=True)
    frappe.db.commit()
    return customer.name