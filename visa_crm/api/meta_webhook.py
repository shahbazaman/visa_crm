import hashlib
import hmac
import json
import frappe
from frappe.utils import now
from visa_crm.api.meta_utils import get_meta_settings, has_doctype, set_if_has, log_info, safe_json_dumps

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
        frappe.response["http_status_code"] = 200
        frappe.response["type"] = "txt"
        log_info("meta_webhook_verified", mode=mode)
        return challenge
    frappe.response["http_status_code"] = 403
    frappe.response["type"] = "txt"
    log_info("meta_webhook_verify_failed", mode=mode, has_token=bool(token), has_settings=bool(settings))
    return "Verification failed"

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
    log_info("meta_webhook_payload_received", payload=payload)
    stored = updates = duplicates = 0
    for item in _webhook_events(payload):
        event_log = _log_webhook_event(item, payload)
        if item.get("event_type") != "leadgen":
            updates += 1
            continue
        existing = _queue_exists(item["source_lead_id"])
        if existing:
            _link_event(event_log, existing, frappe.db.get_value("Lead Intake Queue", existing, "status"))
            duplicates += 1
            continue
        doc = frappe.get_doc({"doctype": "Lead Intake Queue", "status": "Lead Received", "lead_source": _lead_source(), "source_lead_id": item["source_lead_id"], "raw_payload": safe_json_dumps(item)})
        for field, value in {"event_type": item.get("event_type"), "page_id": item.get("page_id"), "form_id": item.get("form_id"), "meta_webhook_event": event_log}.items():
            set_if_has(doc, field, value)
        try:
            doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
            _link_event(event_log, doc.name, "Lead Received")
            stored += 1
        except frappe.DuplicateEntryError:
            duplicates += 1
    frappe.db.commit()
    frappe.response["http_status_code"] = 200
    log_info("meta_webhook_received", stored=stored, updates=updates, duplicates=duplicates)
    return {"ok": True}

def replay_payload(payload):
    stored = updates = duplicates = 0
    for item in _webhook_events(payload):
        event_log = _log_webhook_event(item, payload)
        if item.get("event_type") != "leadgen":
            updates += 1
            continue
        existing = _queue_exists(item["source_lead_id"])
        if existing:
            _link_event(event_log, existing, frappe.db.get_value("Lead Intake Queue", existing, "status"))
            duplicates += 1
            continue
        doc = frappe.get_doc({"doctype": "Lead Intake Queue", "status": "Lead Received", "lead_source": _lead_source(), "source_lead_id": item["source_lead_id"], "raw_payload": safe_json_dumps(item)})
        for field, value in {"event_type": item.get("event_type"), "page_id": item.get("page_id"), "form_id": item.get("form_id"), "meta_webhook_event": event_log}.items():
            set_if_has(doc, field, value)
        doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
        _link_event(event_log, doc.name, "Lead Received")
        stored += 1
    frappe.db.commit()
    return {"ok": True, "stored": stored, "updates": updates, "duplicates": duplicates}

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

def _webhook_events(payload):
    events = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            leadgen_id = value.get("leadgen_id")
            if not leadgen_id:
                continue
            events.append({"event_type": change.get("field"), "source_lead_id": str(leadgen_id), "leadgen_id": str(leadgen_id), "page_id": value.get("page_id") or entry.get("id"), "form_id": value.get("form_id"), "received_at": now(), "payload": payload, "entry": entry, "change": change, "value": value})
    return events

def _lead_events(payload):
    return _webhook_events(payload)

def _queue_exists(source_lead_id):
    return frappe.db.exists("Lead Intake Queue", {"source_lead_id": source_lead_id})

def _lead_source():
    settings = get_meta_settings()
    return (settings.default_lead_source if settings and getattr(settings, "default_lead_source", None) else "Meta Instant Form")

def _log_webhook_event(item, payload):
    request = getattr(frappe.local, "request", None)
    headers = {k: v for k, v in dict(getattr(request, "headers", {}) or {}).items() if k.lower() not in ("authorization", "cookie", "x-hub-signature-256")}
    log_info("meta_webhook_event", event_type=item.get("event_type"), leadgen_id=item.get("leadgen_id"), page_id=item.get("page_id"), form_id=item.get("form_id"), raw_json=payload, headers=headers)
    if not has_doctype("Meta Webhook Event"):
        return None
    doc = frappe.new_doc("Meta Webhook Event")
    values = {"event_type": item.get("event_type"), "leadgen_id": item.get("leadgen_id"), "page_id": item.get("page_id"), "form_id": item.get("form_id"), "raw_json": safe_json_dumps(payload), "request_headers": safe_json_dumps(headers), "received_at": item.get("received_at"), "status": "Received"}
    for field, value in values.items():
        set_if_has(doc, field, value)
    doc.insert(ignore_permissions=True)
    return doc.name

def _link_event(event_log, queue_name=None, queue_status=None):
    if event_log and has_doctype("Meta Webhook Event"):
        frappe.db.set_value("Meta Webhook Event", event_log, {"queue": queue_name, "queue_status": queue_status}, update_modified=False)
