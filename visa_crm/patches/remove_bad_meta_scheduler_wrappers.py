import frappe

TARGET = "visa_crm.api.intake_processor.process_pending"
WRAPPERS = ("call_whitelisted_function", "safe_exec")

def execute():
    deleted = _delete_server_scripts()
    _delete_bad_scheduled_jobs(deleted)

def _delete_server_scripts():
    if not frappe.db.table_exists("Server Script"):
        return set()
    deleted = set()
    fields = ["name"]
    meta = frappe.get_meta("Server Script")
    if meta.has_field("script"):
        fields.append("script")
    if meta.has_field("api_method"):
        fields.append("api_method")
    for row in frappe.get_all("Server Script", fields=fields):
        text = "\n".join(str(row.get(field) or "") for field in fields)
        if TARGET in text:
            deleted.add(row.name)
            frappe.delete_doc("Server Script", row.name, force=1, ignore_permissions=True)
    return deleted

def _delete_bad_scheduled_jobs(deleted_scripts):
    if not frappe.db.table_exists("Scheduled Job Type"):
        return
    meta = frappe.get_meta("Scheduled Job Type")
    fields = [field for field in ("name", "method", "server_script") if meta.has_field(field) or field == "name"]
    for row in frappe.get_all("Scheduled Job Type", fields=fields):
        method = str(row.get("method") or "")
        script = str(row.get("server_script") or "")
        text = f"{method}\n{script}"
        if TARGET in text and any(wrapper in text for wrapper in WRAPPERS) or script in deleted_scripts:
            frappe.delete_doc("Scheduled Job Type", row.name, force=1, ignore_permissions=True)
