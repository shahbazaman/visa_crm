import frappe
from visa_crm.api.meta_utils import has_doctype, has_field

no_cache=1

def get_context(context):
    data=portal_summary()
    context.update(data)
    context.title="Visa Portal"
    return context

@frappe.whitelist()
def portal_summary():
    customer=_customer()
    return {"customer":customer,"profile":_profile(customer),"applications":_applications(customer),"documents":_documents(customer),"payments":_payments(customer),"appointments":_appointments(customer),"timeline":_timeline(customer),"notifications":_notifications()}

def _customer():
    if frappe.session.user=="Guest":
        frappe.throw("Please login to view your visa portal.",frappe.PermissionError)
    email=frappe.session.user.strip().lower()
    filters=[]
    for field in ("email_id","email"):
        if has_field("Customer",field):
            filters.append([field,"=",email])
    if not filters:
        frappe.throw("Customer profile is not linked to this portal user.",frappe.PermissionError)
    customer=frappe.db.get_value("Customer",filters[0],"name")
    if not customer and len(filters)>1:
        customer=frappe.db.get_value("Customer",filters[1],"name")
    if not customer:
        frappe.throw("Customer profile is not linked to this portal user.",frappe.PermissionError)
    return customer

def _profile(customer):
    fields=[f for f in ("name","customer_name","mobile_no","phone","email_id","email") if has_field("Customer",f)]
    return frappe.db.get_value("Customer",customer,fields,as_dict=True) or {"name":customer}

def _applications(customer):
    if not has_doctype("Visa Application"):
        return []
    if not has_field("Visa Application","customer"):
        return []
    fields=[f for f in ("name","customer","lead","visa_type","country","country_interested","status","workflow_state","progress","modified") if has_field("Visa Application",f)]
    return frappe.get_all("Visa Application",filters={"customer":customer},fields=fields,order_by="modified desc",limit_page_length=50)

def _documents(customer):
    if not has_doctype("Customer Documents"):
        return []
    if not has_field("Customer Documents","customer"):
        return []
    fields=[f for f in ("name","customer","document_name","document_type","status","verification_status","expiry_date","file","document_file","modified") if has_field("Customer Documents",f)]
    return frappe.get_all("Customer Documents",filters={"customer":customer},fields=fields,order_by="modified desc",limit_page_length=100)

def _payments(customer):
    if not has_doctype("Payment Schedule"):
        return []
    if not has_field("Payment Schedule","customer"):
        return []
    fields=[f for f in ("name","customer","visa_application","amount","due_date","status","payment_status","paid_amount","modified") if has_field("Payment Schedule",f)]
    return frappe.get_all("Payment Schedule",filters={"customer":customer},fields=fields,order_by="due_date asc",limit_page_length=100)

def _appointments(customer):
    if not has_doctype("ToDo"):
        return []
    return frappe.get_all("ToDo",filters={"reference_type":"Customer","reference_name":customer,"status":["!=","Cancelled"]},fields=["name","description","date","status"],order_by="date asc",limit_page_length=20)

def _timeline(customer):
    if not has_doctype("Communication Event"):
        return []
    if not has_field("Communication Event","customer"):
        return []
    fields=[f for f in ("name","source","event_type","direction","content","summary","event_datetime","modified") if has_field("Communication Event",f)]
    return frappe.get_all("Communication Event",filters={"customer":customer},fields=fields,order_by="event_datetime desc, modified desc",limit_page_length=30)

def _notifications():
    return frappe.get_all("Notification Log",filters={"for_user":frappe.session.user,"read":0},fields=["name","subject","creation"],order_by="creation desc",limit_page_length=20)
