import frappe


def execute():
    if frappe.db.exists("Workspace", "Manager Dashboard"):
        frappe.delete_doc("Workspace", "Manager Dashboard", force=True)
        frappe.db.commit()
