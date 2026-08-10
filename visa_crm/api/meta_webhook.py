import hashlib
import hmac
import json
import frappe
from frappe.utils import now
from werkzeug.wrappers import Response
from visa_crm.api.meta_utils import get_meta_settings, has_doctype, set_if_has, log_info, safe_json_dumps

@frappe.whitelist(allow_guest=True)
def webhook():
    request = getattr(frappe.local, "request", None)
    method = request.method if request else getattr(frappe, "request", None).method if hasattr(frappe, "request") else "GET"
    if method == "GET":
        return meta_verify()
    if method == "POST":
        return receive()
    frappe.response["http_status_code"] = 405
    return {"ok": False, "error": "method_not_allowed"}

def meta_verify():
    request = getattr(frappe.local, "request", None)
    args = getattr(request, "args", {}) if request else getattr(frappe.form_dict, "copy", lambda: {})() or frappe.form_dict
    mode = args.get("hub.mode")
    token = args.get("hub.verify_token")
    challenge = args.get("hub.challenge")
    settings = get_meta_settings()
    saved = _get_password_safe(settings, "verify_token")
    if mode == "subscribe" and token and saved and hmac.compare_digest(token, saved):
        log_info("meta_webhook_verified", mode=mode)
        return Response(challenge or "", status=200, content_type="text/plain; charset=utf-8")
    log_info("meta_webhook_verify_failed", mode=mode, has_token=bool(token), has_settings=bool(settings))
    return Response("Verification failed", status=403, content_type="text/plain; charset=utf-8")

def receive():
    raw = frappe.request.get_data() or b""
    payload = frappe.request.get_json(silent=True) or _decode_json(raw)
    logged_events = {}
    try:
        logged_events = _log_raw_webhook(payload, raw)
        frappe.db.commit()
    except Exception as exc:
        log_info("meta_webhook_raw_log_error", error=str(exc))
        frappe.db.commit()

    if not _valid_signature(raw):
        frappe.response["http_status_code"] = 403
        log_info("meta_webhook_bad_signature", payload_size=len(raw))
        for evt in (logged_events.values() if isinstance(logged_events, dict) else []):
            if evt and has_doctype("Meta Webhook Event"):
                frappe.db.set_value("Meta Webhook Event", evt, "status", "Bad Signature", update_modified=False)
        frappe.db.commit()
        return {"ok": False}

    if not isinstance(payload, dict):
        frappe.response["http_status_code"] = 400
        log_info("meta_webhook_invalid_payload", payload_type=type(payload).__name__)
        frappe.db.commit()
        return {"ok": False}

    log_info("meta_webhook_payload_received", payload=payload)
    stored = updates = duplicates = 0
    new_queues = []
    for item in _webhook_events(payload):
        event_log = logged_events.get(_event_key(item)) or _log_webhook_event(item, payload)
        if item.get("event_type") != "leadgen":
            updates += 1
            continue
        existing = _queue_exists(item["source_lead_id"])
        if existing:
            _link_event(event_log, existing, frappe.db.get_value("Lead Intake Queue", existing, "status"))
            duplicates += 1
            continue
        queue_name, created = _insert_queue(item, event_log)
        _link_event(event_log, queue_name, frappe.db.get_value("Lead Intake Queue", queue_name, "status"))
        if created:
            stored += 1
            new_queues.append(queue_name)
        else:
            duplicates += 1

    frappe.db.commit()

    # Asynchronously enqueue processing for immediate real-time execution
    for qname in new_queues:
        try:
            frappe.enqueue(
                "visa_crm.api.intake_processor.process_queue",
                queue="default",
                docname=qname,
                enqueue_after_commit=False
            )
        except Exception as exc:
            log_info("meta_webhook_enqueue_failed", queue=qname, error=str(exc))

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
        queue_name,created=_insert_queue(item,event_log)
        _link_event(event_log,queue_name,frappe.db.get_value("Lead Intake Queue",queue_name,"status"))
        if created:
            stored += 1
        else:
            duplicates += 1
    frappe.db.commit()
    return {"ok": True, "stored": stored, "updates": updates, "duplicates": duplicates}

def _valid_signature(raw):
    request = getattr(frappe.local, "request", None)
    headers = getattr(request, "headers", {}) if request else {}
    signature = headers.get("X-Hub-Signature-256") or headers.get("x-hub-signature-256") or ""
    if not signature.startswith("sha256="):
        return False
    settings = get_meta_settings()
    secret = _get_password_safe(settings, "meta_app_secret")
    if not secret:
        return False
    digest = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, f"sha256={digest}")

def _get_password_safe(doc, fieldname):
    if not doc or not hasattr(doc, "get_password"):
        return None
    try:
        val = doc.get_password(fieldname, raise_exception=False)
        if val:
            return val
    except Exception:
        pass
    return getattr(doc, fieldname, None)

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
            leadgen_id = value.get("leadgen_id") or value.get("lead_id")
            if not leadgen_id or str(leadgen_id).strip().lower() in ("none", "null", "0", ""):
                continue
            leadgen_id_str = str(leadgen_id)
            events.append({"event_type": change.get("field"), "entry_id": entry.get("id"), "source_lead_id": leadgen_id_str, "leadgen_id": leadgen_id_str, "page_id": value.get("page_id") or entry.get("id"), "form_id": value.get("form_id"), "received_at": now(), "payload": payload, "entry": entry, "change": change, "value": value})
    return events

def _lead_events(payload):
    return _webhook_events(payload)

def _queue_exists(source_lead_id):
    return frappe.db.exists("Lead Intake Queue", {"source_lead_id": source_lead_id})

def _insert_queue(item,event_log=None):
    existing=_queue_exists(item["source_lead_id"])
    if existing:
        return existing,False
    doc=frappe.get_doc({"doctype":"Lead Intake Queue","status":"Lead Received","lead_source":_lead_source(),"source_lead_id":item["source_lead_id"],"raw_payload":safe_json_dumps(item)})
    for field,value in {"event_type":item.get("event_type"),"page_id":item.get("page_id"),"form_id":item.get("form_id"),"meta_webhook_event":event_log}.items():
        set_if_has(doc,field,value)
    try:
        doc.insert(ignore_permissions=True)
        return doc.name,True
    except frappe.DuplicateEntryError:
        canonical=_queue_exists(item["source_lead_id"])
        if not canonical:
            raise
        return canonical,False

def _lead_source():
    settings = get_meta_settings()
    return (settings.default_lead_source if settings and getattr(settings, "default_lead_source", None) else "Meta Instant Form")

def _log_webhook_event(item, payload):
    request = getattr(frappe.local, "request", None)
    headers = dict(getattr(request, "headers", {}) or {})
    log_info("meta_webhook_event", event_type=item.get("event_type"), entry_id=item.get("entry_id"), leadgen_id=item.get("leadgen_id"), page_id=item.get("page_id"), form_id=item.get("form_id"), raw_json=payload, headers=headers)
    if not has_doctype("Meta Webhook Event"):
        return None
    doc = frappe.new_doc("Meta Webhook Event")
    values = {"event_type": item.get("event_type"), "entry_id": item.get("entry_id"), "leadgen_id": item.get("leadgen_id"), "page_id": item.get("page_id"), "form_id": item.get("form_id"), "raw_json": safe_json_dumps(payload), "request_headers": safe_json_dumps(headers), "received_at": item.get("received_at"), "status": "Received"}
    for field, value in values.items():
        set_if_has(doc, field, value)
    doc.insert(ignore_permissions=True)
    return doc.name

def _link_event(event_log, queue_name=None, queue_status=None):
    if event_log and has_doctype("Meta Webhook Event"):
        frappe.db.set_value("Meta Webhook Event", event_log, {"queue": queue_name, "queue_status": queue_status}, update_modified=False)

def _log_raw_webhook(payload, raw):
    events = _webhook_events(payload) if isinstance(payload, dict) else []
    if not events:
        item = {"event_type": None, "entry_id": None, "leadgen_id": None, "page_id": None, "form_id": None, "received_at": now()}
        name = _log_webhook_event(item, payload if isinstance(payload, dict) else {"raw": raw.decode("utf-8", "replace")})
        return {_event_key(item): name} if name else {}
    logged = {}
    for item in events:
        name = _log_webhook_event(item, payload)
        if name:
            logged[_event_key(item)] = name
    return logged

def _event_key(item):
    return "|".join(str(item.get(field) or "") for field in ("event_type", "entry_id", "leadgen_id", "page_id", "form_id"))
