import frappe

def execute():
    # 1. Purge conflicting Workspaces
    workspaces = frappe.get_all(
        "Workspace",
        filters={"name": ["in", ["Employee Dashboard", "employee-dashboard", "Employee Performance Dashboard", "employee-performance-dashboard"]]},
        pluck="name",
    )
    workspaces += frappe.get_all(
        "Workspace",
        filters={"label": ["in", ["Employee Dashboard", "Employee Performance Dashboard"]]},
        pluck="name",
    )
    for ws in set(workspaces):
        frappe.db.delete("Workspace", {"name": ws})

    # 2. Ensure Page employee-performance-dashboard is registered
    if not frappe.db.exists("Page", "employee-performance-dashboard"):
        doc = frappe.get_doc({
            "doctype": "Page",
            "name": "employee-performance-dashboard",
            "page_name": "employee-performance-dashboard",
            "title": "Employee Performance & Investigation Dashboard",
            "module": "Visa CRM",
            "standard": "Yes",
            "icon": "users",
            "roles": [
                {"role": "System Manager"},
                {"role": "Sales Manager"},
                {"role": "General Manager"},
                {"role": "Managing Director"},
                {"role": "MD"},
                {"role": "CRM Manager"}
            ]
        })
        doc.insert(ignore_permissions=True, ignore_if_duplicate=True)

    # 3. Add shortcut to Visa CRM Workspace
    if frappe.db.exists("Workspace", "Visa CRM"):
        ws_doc = frappe.get_doc("Workspace", "Visa CRM")
        shortcuts = ws_doc.get("shortcuts") or []
        if not any(s.get("label") == "Employee Performance Dashboard" or s.get("link_to") == "employee-performance-dashboard" for s in shortcuts):
            ws_doc.append("shortcuts", {
                "label": "Employee Performance Dashboard",
                "type": "Page",
                "link_to": "employee-performance-dashboard",
                "link_type": "Page"
            })
            ws_doc.save(ignore_permissions=True)

    frappe.db.commit()
    frappe.clear_cache()
