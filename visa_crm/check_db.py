import frappe

def execute():
    fields = frappe.db.sql("DESC `tabCRM Lead`", as_dict=True)
    found = False
    for f in fields:
        if f.get("Field") in ("lead_category", "lead_group"):
            print(f["Field"], "->", f["Type"])
            found = True
    if not found:
        print("Fields not found")
