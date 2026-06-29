import frappe

def after_install():
    create_employee_workspace()

def create_employee_workspace():

    if frappe.db.exists("Workspace","Employee Dashboard"):
        return

    workspace=frappe.get_doc({
        "doctype":"Workspace",
        "title":"Employee Dashboard",
        "label":"Employee Dashboard",
        "module":"Visa CRM",
        "public":1,
        "is_hidden":0
    })

    workspace.insert(ignore_permissions=True)

    frappe.db.commit()