import frappe
from visa_crm.api.communication_center import conversation, send_message, shared_inbox
from visa_crm.www.visa_portal import portal_summary

@frappe.whitelist()
def inbox(filters=None,limit=50):
    _staff()
    return shared_inbox(filters,limit)

@frappe.whitelist()
def get_inbox(filters=None,limit=50):
    _staff()
    return inbox(filters,limit)

@frappe.whitelist()
def thread(event):
    _staff()
    return conversation(event)

@frappe.whitelist()
def reply(channel,to,content,customer=None,lead=None,visa_application=None):
    _staff()
    return send_message(channel,to,content,customer=customer,lead=lead,visa_application=visa_application,assigned_to=frappe.session.user)

@frappe.whitelist()
def my_portal():
    return portal_summary()

def _staff():
    if frappe.session.user=="Guest" or not ({"System Manager","Sales Manager","Counselor","Visa Processing","Administrator"} & set(frappe.get_roles())):
        frappe.throw("Visa CRM staff access required", frappe.PermissionError)
