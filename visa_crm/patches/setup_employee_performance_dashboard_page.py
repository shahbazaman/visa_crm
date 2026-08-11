import frappe

ROLES = [
    {"role": "System Manager"},
    {"role": "Sales Manager"},
    {"role": "General Manager"},
    {"role": "Managing Director"},
    {"role": "MD"},
    {"role": "CRM Manager"}
]

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

    # 2. Ensure Page employee-performance-dashboard and employee-dashboard are registered with roles
    for p_name, p_title in (
        ("employee-performance-dashboard", "Employee Performance & Investigation Dashboard"),
        ("employee-dashboard", "Employee Dashboard")
    ):
        if not frappe.db.exists("Page", p_name):
            doc = frappe.get_doc({
                "doctype": "Page",
                "name": p_name,
                "page_name": p_name,
                "title": p_title,
                "module": "Visa CRM",
                "standard": "Yes",
                "icon": "users",
                "roles": ROLES
            })
            doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
        else:
            page_doc = frappe.get_doc("Page", p_name)
            existing_roles = {r.role for r in page_doc.roles}
            updated = False
            for r in ROLES:
                if r["role"] not in existing_roles:
                    page_doc.append("roles", r)
                    updated = True
            if updated:
                page_doc.save(ignore_permissions=True)

    # 3. Add shortcuts to Visa CRM Workspace
    if frappe.db.exists("Workspace", "Visa CRM"):
        ws_doc = frappe.get_doc("Workspace", "Visa CRM")
        shortcuts = ws_doc.get("shortcuts") or []
        existing_links = {s.get("link_to") for s in shortcuts}

        if "employee-dashboard" not in existing_links:
            ws_doc.append("shortcuts", {
                "label": "Employee Dashboard",
                "type": "Page",
                "link_to": "employee-dashboard",
                "link_type": "Page"
            })
        if "employee-performance-dashboard" not in existing_links:
            ws_doc.append("shortcuts", {
                "label": "Employee Performance Dashboard",
                "type": "Page",
                "link_to": "employee-performance-dashboard",
                "link_type": "Page"
            })
        ws_doc.save(ignore_permissions=True)

    frappe.db.commit()
    frappe.clear_cache()
