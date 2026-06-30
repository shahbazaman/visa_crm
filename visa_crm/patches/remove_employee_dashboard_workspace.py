import frappe


def execute():
    if frappe.db.exists("Workspace", "Employee Dashboard"):
        frappe.delete_doc("Workspace", "Employee Dashboard", force=True)
        frappe.db.commit()
