import frappe


def execute():
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

    for workspace in set(workspaces):
        frappe.db.delete("Workspace", {"name": workspace})

    frappe.db.commit()