import frappe

from visa_crm.manager_dashboard.dashboard import build_dashboard

@frappe.whitelist()

def dashboard():

    return build_dashboard()