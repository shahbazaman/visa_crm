import frappe
from visa_crm.api.meta_utils import has_field

def find_customer(phone=None,email=None,name=None):
    if phone:
        for field in ("mobile_no","whatsapp_no"):
            if has_field("Customer",field):
                customer=frappe.db.get_value("Customer",{field:phone},"name")
                if customer:
                    return customer
    if email:
        if has_field("Customer","email_id"):
            customer=frappe.db.get_value("Customer",{"email_id":email},"name")
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

def create_customer_from_lead(lead,data=None):
    data=data or {}
    doc=frappe.get_doc("CRM Lead",lead)
    values=dict(data)
    values["customer_name"]=data.get("customer_name") or doc.lead_name or doc.first_name
    values["phone"]=data.get("phone") or getattr(doc,"mobile_no",None)
    values["email"]=data.get("email") or getattr(doc,"email",None)
    return create_customer(values)

def create_customer(data):
    data=data or {}
    name=data.get("customer_name") or f"Meta Lead {data.get('source_lead_id') or ''}".strip()
    phone=data.get("phone")
    email=data.get("email")
    existing=find_customer(phone,email)
    if existing:
        return existing
    customer=frappe.new_doc("Customer")
    values={"customer_name":name,"customer_type":"Individual","mobile_no":phone,"whatsapp_no":data.get("whatsapp") or phone,"email_id":email}
    for field,value in values.items():
        if value is not None and customer.meta.has_field(field):
            customer.set(field,value)
    try:
        customer.insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        existing=find_customer(phone,email)
        if existing:
            return existing
        raise
    return customer.name
