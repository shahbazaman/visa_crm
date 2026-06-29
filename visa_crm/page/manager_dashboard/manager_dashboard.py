import frappe

@frappe.whitelist()
def get_dashboard():

    from visa_crm.manager_dashboard.dashboard import build_dashboard

    return build_dashboard()