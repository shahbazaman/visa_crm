import hashlib
import hmac
import json
import frappe
from visa_crm.api.meta_utils import get_meta_settings, log_info, safe_json_dumps

@frappe.whitelist(allow_guest=True)
def webhook():
    if frappe.request.method == "GET":
        return meta_verify()
    if frappe.request.method == "POST":
        return receive()
    frappe.response["http_status_code"] = 405
    return {"ok": False, "error": "method_not_allowed"}

def meta_verify():
    mode = frappe.request.args.get("hub.mode")
    token = frappe.request.args.get("hub.verify_token")
    challenge = frappe.request.args.get("hub.challenge")
    settings = get_meta_settings()
    saved = settings.get_password("verify_token") if settings else None
    if mode == "subscribe" and token and saved and hmac.compare_digest(token, saved):
        frappe.response.update({"type": "txt", "doctype": "meta", "filename": "challenge", "result": challenge})
        log_info("meta_webhook_verified", mode=mode)
        return
    frappe.response["http_status_code"] = 403
    frappe.response.update({"type": "txt", "doctype": "meta", "filename": "error", "result": "Verification failed"})
    log_info("meta_webhook_verify_failed", mode=mode, has_token=bool(token), has_settings=bool(settings))

def receive():
    raw = frappe.request.get_data() or b""
    if not _valid_signature(raw):
        frappe.response["http_status_code"] = 403
        log_info("meta_webhook_bad_signature", payload_size=len(raw))
        return {"ok": False}
    payload = frappe.request.get_json(silent=True) or _decode_json(raw)
    if not isinstance(payload, dict):
        frappe.response["http_status_code"] = 400
        log_info("meta_webhook_invalid_payload", payload_type=type(payload).__name__)
        return {"ok": False}
    stored = duplicates = 0
    for item in _lead_events(payload):
        if _queue_exists(item["source_lead_id"]):
            duplicates += 1
            continue
        doc = frappe.get_doc({"doctype": "Lead Intake Queue", "status": "Lead Received", "lead_source": _lead_source(), "source_lead_id": item["source_lead_id"], "raw_payload": safe_json_dumps(item)})
        try:
            doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
            stored += 1
        except frappe.DuplicateEntryError:
            duplicates += 1
    frappe.db.commit()
    log_info("meta_webhook_received", stored=stored, duplicates=duplicates)
    return {"ok": True}

def _valid_signature(raw):
    signature = frappe.request.headers.get("X-Hub-Signature-256") or ""
    if not signature.startswith("sha256="):
        return False
    settings = get_meta_settings()
    secret = settings.get_password("meta_app_secret") if settings else None
    if not secret:
        return False
    digest = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, f"sha256={digest}")

def _decode_json(raw):
    try:
        return json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        log_info("meta_webhook_json_decode_failed", error=str(exc))
        return {}

def _lead_events(payload):
    events = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            leadgen_id = value.get("leadgen_id")
            if not leadgen_id:
                continue
            events.append({"source_lead_id": str(leadgen_id), "payload": payload, "entry": entry, "change": change, "value": value})
    return events

def _queue_exists(source_lead_id):
    return frappe.db.exists("Lead Intake Queue", {"source_lead_id": source_lead_id})

def _lead_source():
    settings = get_meta_settings()
    return (settings.default_lead_source if settings and getattr(settings, "default_lead_source", None) else "Meta Instant Form")
