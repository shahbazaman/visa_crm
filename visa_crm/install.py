import frappe

def after_install():
    remove_employee_workspace()

def remove_employee_workspace():
    workspaces = frappe.get_all(
        "Workspace",
        filters={"name": ["in", ["Employee Dashboard", "employee-dashboard"]]},
        pluck="name",
    )
    workspaces += frappe.get_all(
        "Workspace",
        filters={"label": "Employee Dashboard"},
        pluck="name",
    )
    for ws in set(workspaces):
        frappe.db.delete("Workspace", {"name": ws})

    frappe.db.commit()