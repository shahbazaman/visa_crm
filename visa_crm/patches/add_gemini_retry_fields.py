import frappe
from frappe.utils import add_to_date, now_datetime

STATUS = "Gemini Retry Scheduled"
PAUSED_STATUS = "Gemini Rate Limit Paused"
MAX_RETRIES = 5

def execute():
    if not frappe.db.exists("DocType", "Call Intelligence"):
        return
    _status_options()
    _repair_existing_rate_limits()
    frappe.db.commit()

def _status_options():
    row = frappe.db.get_value("DocField", {"parent": "Call Intelligence", "fieldname": "processing_status"}, ["name", "options"], as_dict=True)
    if not row:
        return
    options = [item for item in (row.options or "").split("\n") if item]
    changed = False
    for status in (STATUS, PAUSED_STATUS):
        if status not in options:
            options.append(status)
            changed = True
    if changed:
        frappe.db.set_value("DocField", row.name, "options", "\n".join(options), update_modified=False)

def _repair_existing_rate_limits():
    meta = frappe.get_meta("Call Intelligence")
    fields = ["name", "retry_count"]
    if meta.has_field("next_retry_at"):
        fields.append("next_retry_at")
    rows = frappe.get_all("Call Intelligence", filters={"processing_status": ["in", ["Failed Transcription", "Failed Upload to Gemini", "Failed to Upload"]]}, fields=fields, limit=1000)
    for row in rows:
        error = frappe.db.get_value("Call Intelligence", row.name, "ai_error") or ""
        if not _is_rate_limit(error):
            continue
        count = min((row.retry_count or 0) + 1, MAX_RETRIES)
        retry_at = add_to_date(now_datetime(), minutes=min(240, 15 * (2 ** max(count - 1, 0))))
        values = {"processing_status": STATUS, "retry_count": count, "ai_error": _sanitize(error)}
        if meta.has_field("next_retry_at"):
            values["next_retry_at"] = retry_at
        frappe.db.set_value("Call Intelligence", row.name, values, update_modified=False)

def _is_rate_limit(error):
    text = str(error or "").lower()
    return "429" in text or "too many requests" in text or "quota" in text or "rate limit" in text

def _sanitize(error):
    text = str(error or "")
    if "?key=" in text:
        text = text.split("?key=")[0]
    return text[:1000]
