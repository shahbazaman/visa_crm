import os
import frappe
from frappe.utils import now
from visa_crm.api.meta_graph import MetaGraphError, fetch_lead
from visa_crm.api.meta_utils import get_meta_settings, has_doctype, has_field, load_json, safe_json_dumps

CRM_SYNC_METHOD = "crm.lead_syncing.background_sync.sync_leads_from_all_enabled_sources"

@frappe.whitelist()
def generate_report(queue_name=None, leadgen_id=None, write_file=1):
    _admin()
    report = audit(queue_name=queue_name, leadgen_id=leadgen_id)
    if int(write_file or 0):
        _write_report(report)
    return report

@frappe.whitelist()
def webhook_audit():
    _admin()
    return last_webhook_events()

@frappe.whitelist()
def last_webhook_events():
    _admin()
    if not has_doctype("Meta Webhook Event"):
        return []
    fields = ["name", "creation"] + [field for field in ("event_type", "entry_id", "leadgen_id", "page_id", "form_id", "request_headers", "raw_json", "queue", "queue_status", "crm_lead", "customer", "visa_application", "communication_event", "graph_api_request", "graph_api_response") if has_field("Meta Webhook Event", field)]
    rows = frappe.get_all("Meta Webhook Event", fields=fields, order_by="creation desc", limit=20)
    out = []
    for row in rows:
        queue = row.get("queue")
        queue_status = row.get("queue_status")
        lead = row.get("crm_lead")
        if queue and has_doctype("Lead Intake Queue"):
            queue_status = queue_status or frappe.db.get_value("Lead Intake Queue", queue, "status")
            lead = lead or (frappe.db.get_value("Lead Intake Queue", queue, "matched_lead") if has_field("Lead Intake Queue", "matched_lead") else None)
        pipe = _pipeline_row(queue) if queue else {}
        out.append({"event": row.name, "received_at": row.creation, "event_field": row.get("event_type"), "entry_id": row.get("entry_id"), "leadgen_id": row.get("leadgen_id"), "page_id": row.get("page_id"), "form_id": row.get("form_id"), "headers": load_json(row.get("request_headers"), {}), "raw_json": load_json(row.get("raw_json"), {}), "graph_request": row.get("graph_api_request"), "graph_response": row.get("graph_api_response"), "queue": queue, "queue_status": queue_status, "crm_lead_created": bool(lead), "crm_lead": lead, "customer": row.get("customer") or pipe.get("customer"), "visa_application": row.get("visa_application") or pipe.get("visa_application"), "communication_event": row.get("communication_event") or pipe.get("communication_event"), "processing_time": pipe.get("processing_time")})
    return out

@frappe.whitelist()
def last_real_leadgen():
    _admin()
    if not has_doctype("Meta Webhook Event"):
        return {"found": False, "message": "No real Meta LeadGen webhook has ever been received."}
    fields = ["name", "creation"] + [field for field in ("event_type", "entry_id", "leadgen_id", "page_id", "form_id", "request_headers", "raw_json", "queue", "queue_status", "crm_lead", "graph_api_request", "graph_api_response") if has_field("Meta Webhook Event", field)]
    rows = frappe.get_all("Meta Webhook Event", filters={"event_type": "leadgen"}, fields=fields, order_by="creation desc", limit=1)
    if not rows:
        return {"found": False, "message": "No real Meta LeadGen webhook has ever been received."}
    row = rows[0]
    graph = _graph_probe(row.get("leadgen_id")) if row.get("leadgen_id") else {"skipped": "missing_leadgen_id"}
    if graph.get("ok") is False:
        _store_event_graph(row.name, graph)
    return {"found": True, "event": row.name, "received_at": row.creation, "event_field": row.get("event_type"), "entry_id": row.get("entry_id"), "leadgen_id": row.get("leadgen_id"), "page_id": row.get("page_id"), "form_id": row.get("form_id"), "headers": load_json(row.get("request_headers"), {}), "raw_json": load_json(row.get("raw_json"), {}), "queue": row.get("queue"), "queue_status": row.get("queue_status"), "crm_lead_created": bool(row.get("crm_lead")), "crm_lead": row.get("crm_lead"), "graph_probe": graph}

@frappe.whitelist()
def meta_health():
    _admin()
    settings = get_meta_settings()
    today = frappe.utils.today()
    data = {"webhook_reachable": True, "webhook_receiving_events": False, "leadgen_events_count": 0, "leadgen_update_count": 0, "graph_success_count": 0, "graph_failed_count": 0, "crm_leads_created": 0, "ignored_test_events": 0, "queue_waiting": 0, "queue_failed": 0, "queue_ignored": 0, "permission_failures": 0, "token_expiry": getattr(settings, "token_expiry", None) if settings else None, "page_id": getattr(settings, "page_id", None) if settings else None, "form_ids": getattr(settings, "lead_form_ids", None) if settings else None, "last_webhook_received": None, "last_real_webhook": None, "last_leadgen_event": None, "last_leadgen_update": None, "last_successful_graph_download": None, "last_crm_lead_created": None, "last_customer_created": None, "last_visa_created": None, "last_queue_processed": None, "crm_leads_created_today": 0}
    if has_doctype("Meta Webhook Event"):
        data["webhook_receiving_events"] = bool(frappe.db.count("Meta Webhook Event"))
        data["leadgen_events_count"] = frappe.db.count("Meta Webhook Event", {"event_type": "leadgen"})
        data["leadgen_update_count"] = frappe.db.count("Meta Webhook Event", {"event_type": "leadgen_update"})
        data["last_webhook_received"] = _latest_value("Meta Webhook Event", None, "received_at")
        data["last_leadgen_event"] = _latest_value("Meta Webhook Event", {"event_type": "leadgen"}, "received_at")
        data["last_real_webhook"] = data["last_leadgen_event"]
        data["last_leadgen_update"] = _latest_value("Meta Webhook Event", {"event_type": "leadgen_update"}, "received_at")
    if has_doctype("Lead Intake Queue"):
        data["queue_waiting"] = frappe.db.count("Lead Intake Queue", {"status": "Lead Received"})
        data["queue_failed"] = frappe.db.count("Lead Intake Queue", {"status": "Failed"})
        data["queue_ignored"] = frappe.db.count("Lead Intake Queue", {"status": "Ignored Test Event"})
        data["ignored_test_events"] = data["queue_ignored"]
        if has_field("Lead Intake Queue", "graph_payload"):
            data["graph_success_count"] = frappe.db.count("Lead Intake Queue", {"graph_payload": ["is", "set"], "status": ["!=", "Failed"]})
        if has_field("Lead Intake Queue", "graph_error_message"):
            data["graph_failed_count"] = frappe.db.count("Lead Intake Queue", {"graph_error_message": ["is", "set"]})
            data["permission_failures"] = _permission_failures()
        if has_field("Lead Intake Queue", "matched_lead"):
            data["crm_leads_created"] = frappe.db.count("Lead Intake Queue", {"matched_lead": ["is", "set"]})
        data["last_successful_graph_download"] = _latest_value("Lead Intake Queue", {"graph_payload": ["is", "set"]}, "modified") if has_field("Lead Intake Queue", "graph_payload") else None
        data["last_queue_processed"] = _latest_value("Lead Intake Queue", {"status": "Processed"}, "modified")
    if has_doctype("CRM Lead"):
        data["crm_leads_created_today"] = frappe.db.count("CRM Lead", {"creation": [">=", today]})
        data["last_crm_lead_created"] = _latest_value("CRM Lead", None, "creation")
    if has_doctype("Customer"):
        data["last_customer_created"] = _latest_value("Customer", None, "creation")
    if has_doctype("Visa Application"):
        data["last_visa_created"] = _latest_value("Visa Application", None, "creation")
    return data

@frappe.whitelist()
def replay_webhook_event(event_name):
    _admin()
    if not has_doctype("Meta Webhook Event"):
        frappe.throw("Meta Webhook Event is not installed")
    raw = frappe.db.get_value("Meta Webhook Event", event_name, "raw_json")
    payload = load_json(raw, {})
    if not payload:
        frappe.throw("Stored webhook JSON is empty")
    from visa_crm.api import meta_webhook
    result = meta_webhook.replay_payload(payload)
    return {"replayed": event_name, "result": result, "note": "Replay inserts queue from stored webhook JSON only and never calls Meta Graph API directly."}

@frappe.whitelist()
def graph_preview(leadgen_id):
    _admin()
    if not leadgen_id:
        frappe.throw("leadgen_id is required")
    graph = _graph_probe(leadgen_id)
    response = graph.get("response") or {}
    return {"ok": graph.get("ok"), "leadgen_id": leadgen_id, "field_data": response.get("field_data") or [], "response": response, "request": graph.get("request"), "error": graph.get("error")}

@frappe.whitelist()
def download_test_lead(leadgen_id):
    _admin()
    if not leadgen_id:
        frappe.throw("leadgen_id is required")
    graph = _graph_probe(leadgen_id)
    if not graph.get("ok"):
        return {"ok": False, "stage": "graph", "graph": graph}
    queue = _queue_from_leadgen(leadgen_id, graph.get("response"))
    from visa_crm.api.intake_processor import process_queue
    process_queue(queue)
    result = _pipeline_row(queue)
    visa = _ensure_visa_application(result)
    if visa:
        result = _pipeline_row(queue)
    return {"ok": True, "queue": queue, "graph": graph, "pipeline": result}

@frappe.whitelist()
def replay_pipeline(leadgen_id):
    return download_test_lead(leadgen_id)

@frappe.whitelist()
def event_detail(event_name):
    _admin()
    if not has_doctype("Meta Webhook Event"):
        frappe.throw("Meta Webhook Event is not installed")
    fields = ["name", "creation"] + [field for field in ("event_type", "entry_id", "leadgen_id", "page_id", "form_id", "raw_json", "request_headers", "graph_api_request", "graph_api_response", "queue", "queue_status", "crm_lead", "customer", "visa_application", "communication_event") if has_field("Meta Webhook Event", field)]
    row = frappe.db.get_value("Meta Webhook Event", event_name, fields, as_dict=True)
    if not row:
        frappe.throw("Meta Webhook Event not found")
    queue = row.get("queue")
    pipe = _pipeline_row(queue) if queue else {}
    raw = load_json(row.get("raw_json"), {})
    return {"event": row.name, "event_type": row.get("event_type"), "entry_id": row.get("entry_id"), "leadgen_id": row.get("leadgen_id"), "page_id": row.get("page_id"), "form_id": row.get("form_id"), "raw_payload": raw, "parsed_payload": _parsed_payload(raw), "headers": load_json(row.get("request_headers"), {}), "graph_request": load_json(row.get("graph_api_request"), {}) if row.get("graph_api_request") else None, "graph_response": load_json(row.get("graph_api_response"), {}) if row.get("graph_api_response") else None, "queue": queue, "crm_lead": row.get("crm_lead") or pipe.get("lead"), "customer": row.get("customer") or pipe.get("customer"), "visa_application": row.get("visa_application") or pipe.get("visa_application"), "communication_event": row.get("communication_event") or pipe.get("communication_event"), "pipeline": pipe}

@frappe.whitelist()
def intake_pipeline(queue_name=None):
    _admin()
    if queue_name:
        return _timeline(queue_name)
    if not has_doctype("Lead Intake Queue"):
        return []
    rows = frappe.get_all("Lead Intake Queue", fields=["name"], order_by="modified desc", limit=20)
    return [_timeline(row.name) for row in rows]

def _admin():
    if "System Manager" not in frappe.get_roles():
        frappe.throw("System Manager role required", frappe.PermissionError)

def audit(queue_name=None, leadgen_id=None):
    latest = _queue(queue_name)
    leadgen_id = leadgen_id or (latest.get("source_lead_id") if latest else None)
    report = {
        "official_crm_scheduler": _crm_scheduler(),
        "lead_sync_sources": _lead_sync_sources(),
        "custom_pipeline": _custom_pipeline(),
        "meta_settings": _settings_status(),
        "latest_queue": latest,
        "graph_probe": _graph_probe(leadgen_id) if leadgen_id else {"skipped": "no_leadgen_id"},
        "blockers": []
    }
    report["active_pipeline"] = _active_pipeline(report)
    report["built_in_crm_sync_status"] = _built_in_status(report)
    report["queue_failure_reason"] = _failure_reason(report)
    report["app_review_or_config"] = _classify_graph_failure(report["graph_probe"])
    report["blockers"] = _blockers(report)
    return report

def _crm_scheduler():
    out = {"method": CRM_SYNC_METHOD, "found": False, "rows": []}
    if not has_doctype("Scheduled Job Type"):
        return out
    meta = frappe.get_meta("Scheduled Job Type")
    if not meta.has_field("method"):
        return out
    fields = ["name", "method"] + [field for field in ("stopped", "disabled", "frequency", "cron_format") if meta.has_field(field)]
    rows = frappe.get_all("Scheduled Job Type", filters={"method": CRM_SYNC_METHOD}, fields=fields)
    out.update({"found": bool(rows), "rows": rows, "active": any(not row.get("stopped") and not row.get("disabled") for row in rows)})
    return out

def _lead_sync_sources():
    out = {"doctype_exists": has_doctype("Lead Sync Source"), "meta_rows": [], "other_enabled_rows": []}
    if not out["doctype_exists"]:
        return out
    meta = frappe.get_meta("Lead Sync Source")
    fields = ["name"] + [field for field in ("source", "type", "platform", "lead_source", "title", "provider", "enabled", "disabled", "lead_gen_form", "leadgen_form", "lead_gen_form_id", "form_id") if meta.has_field(field)]
    rows = frappe.get_all("Lead Sync Source", fields=fields)
    meta_names = set()
    for row in rows:
        if _is_meta_row(row):
            meta_names.add(row.name)
            out["meta_rows"].append(row)
        elif _is_enabled(row):
            out["other_enabled_rows"].append(row)
    return out

def _custom_pipeline():
    hooks_ok = False
    try:
        import visa_crm.hooks as hooks
        cron = (getattr(hooks, "scheduler_events", {}) or {}).get("cron") or {}
        methods = [method for jobs in cron.values() for method in jobs]
        hooks_ok = "visa_crm.api.intake_processor.process_pending" in methods
    except Exception:
        hooks_ok = False
    return {"webhook": "visa_crm.api.meta_webhook.webhook", "queue_doctype": has_doctype("Lead Intake Queue"), "scheduler_method": "visa_crm.api.intake_processor.process_pending", "scheduler_in_hooks": hooks_ok, "active": bool(hooks_ok and has_doctype("Lead Intake Queue"))}

def _settings_status():
    settings = get_meta_settings()
    if not settings:
        return {"exists": False}
    token = _meta_token(settings)
    return {"exists": True, "has_page_access_token": bool(token), "page_id": getattr(settings, "page_id", None), "lead_form_ids": getattr(settings, "lead_form_ids", None), "has_app_secret": bool(_safe_password(settings, "meta_app_secret")), "has_verify_token": bool(_safe_password(settings, "verify_token"))}

def _safe_password(doc, fieldname):
    try:
        return doc.get_password(fieldname, raise_exception=False)
    except Exception:
        return None

def _meta_token(settings):
    for field in ("access_token", "page_access_token", "facebook_page_access_token", "meta_page_access_token"):
        token = _safe_password(settings, field) or getattr(settings, field, None)
        if token:
            return token
    return frappe.conf.get("meta_page_access_token") or frappe.conf.get("facebook_page_access_token") or frappe.conf.get("page_access_token")

def _latest_value(doctype, filters, field):
    if not has_field(doctype, field):
        field = "creation"
    rows = frappe.get_all(doctype, filters=filters or {}, fields=["name", field], order_by=f"{field} desc", limit=1)
    return rows[0].get(field) if rows else None

def _permission_failures():
    rows = frappe.get_all("Lead Intake Queue", fields=["name", "graph_error_message"], filters={"graph_error_message": ["is", "set"]}, limit=500)
    return len([row for row in rows if "permission" in str(row.get("graph_error_message") or "").lower() or "oauth" in str(row.get("graph_error_message") or "").lower()])

def _store_event_graph(event_name, graph):
    if not has_doctype("Meta Webhook Event"):
        return
    values = {}
    if has_field("Meta Webhook Event", "graph_api_request"):
        values["graph_api_request"] = safe_json_dumps(graph.get("request"))
    if has_field("Meta Webhook Event", "graph_api_response"):
        values["graph_api_response"] = safe_json_dumps(graph.get("response"))
    if values:
        frappe.db.set_value("Meta Webhook Event", event_name, values, update_modified=False)

def _queue(name=None):
    if not has_doctype("Lead Intake Queue"):
        return None
    fields = ["name", "status", "source_lead_id", "creation", "modified"] + [field for field in ("retry_count", "last_error", "graph_payload", "graph_api_request", "graph_api_response", "page_id", "form_id", "matched_lead", "matched_customer", "communication_event", "followup_reference") if has_field("Lead Intake Queue", field)]
    if name:
        return frappe.db.get_value("Lead Intake Queue", name, fields, as_dict=True)
    rows = frappe.get_all("Lead Intake Queue", fields=fields, order_by="modified desc", limit=1)
    return rows[0] if rows else None

def _graph_probe(leadgen_id):
    try:
        response = fetch_lead(leadgen_id, get_meta_settings(), {"source_lead_id": leadgen_id, "status": "audit"})
        return {"ok": True, "response": response}
    except MetaGraphError as exc:
        return {"ok": False, "error": str(exc), "status_code": exc.status_code, "request": exc.request, "response": exc.response}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "traceback": frappe.get_traceback()}

def _active_pipeline(report):
    custom = report["custom_pipeline"].get("active")
    crm = report["official_crm_scheduler"].get("active")
    meta_rows = [row for row in report["lead_sync_sources"].get("meta_rows", []) if _is_enabled(row)]
    if custom and not crm and not meta_rows:
        return "custom_visa_crm_only"
    if custom and (crm or meta_rows):
        return "duplicate_possible_custom_and_builtin_crm"
    if crm or meta_rows:
        return "builtin_crm_only"
    return "none"

def _built_in_status(report):
    if report["lead_sync_sources"].get("meta_rows"):
        active = [row.name for row in report["lead_sync_sources"]["meta_rows"] if _is_enabled(row)]
        return "disabled" if not active else f"active_meta_sources:{','.join(active)}"
    scheduler = report["official_crm_scheduler"]
    return "scheduler_stopped" if scheduler.get("found") and not scheduler.get("active") else ("scheduler_active" if scheduler.get("active") else "not_found")

def _failure_reason(report):
    queue = report.get("latest_queue") or {}
    probe = report.get("graph_probe") or {}
    if queue.get("status") == "Failed":
        return queue.get("last_error") or probe.get("error")
    if probe.get("ok") is False:
        return probe.get("error")
    return None

def _classify_graph_failure(probe):
    if probe.get("ok"):
        return "graph_api_ok"
    text = safe_json_dumps(probe).lower()
    if "permission" in text or "permissions" in text or "app review" in text or "access to this endpoint" in text:
        return "likely_meta_app_review_or_permission_restriction"
    if "oauth" in text or "token" in text or "session" in text:
        return "likely_token_or_oauth_configuration"
    if "unsupported get request" in text or "object does not exist" in text:
        return "likely_wrong_leadgen_id_page_or_token_scope"
    if "page access token is not configured" in text:
        return "missing_page_access_token"
    return "unknown_graph_or_configuration_error"

def _blockers(report):
    blockers = []
    if report["active_pipeline"] != "custom_visa_crm_only":
        blockers.append(f"pipeline_state:{report['active_pipeline']}")
    settings = report["meta_settings"]
    if not settings.get("exists"):
        blockers.append("Meta Settings record is missing")
    if not settings.get("has_page_access_token"):
        blockers.append("Meta Page Access Token is missing")
    if not settings.get("page_id"):
        blockers.append("Meta Page ID is missing")
    if not settings.get("lead_form_ids"):
        blockers.append("Meta lead form IDs are missing")
    probe = report["graph_probe"]
    if probe.get("ok") is False:
        blockers.append(f"Graph API failure:{probe.get('error')}")
    queue = report.get("latest_queue") or {}
    if queue.get("status") == "Failed" and queue.get("last_error"):
        blockers.append(f"Queue failed:{queue.get('last_error')}")
    return blockers

def _is_meta_row(row):
    text = " ".join(str(row.get(field) or "") for field in row.keys()).lower()
    return any(token in text for token in ("meta", "facebook", "fb", "instagram"))

def _is_enabled(row):
    if "enabled" in row and row.get("enabled") is not None:
        return bool(row.get("enabled"))
    if "disabled" in row and row.get("disabled") is not None:
        return not bool(row.get("disabled"))
    return True

def _write_report(report):
    path = frappe.get_app_path("visa_crm", "..", "META_INTEGRATION_AUDIT.md")
    lines = ["# Meta Integration Audit", "", f"- Active pipeline: `{report['active_pipeline']}`", f"- Built-in CRM sync status: `{report['built_in_crm_sync_status']}`", f"- Queue failure reason: `{report.get('queue_failure_reason') or 'none'}`", f"- App Review/config classification: `{report['app_review_or_config']}`", "", "## Exact Graph API Response", "", "```json", safe_json_dumps(report.get("graph_probe")), "```", "", "## Remaining Blockers"]
    lines += [f"- {blocker}" for blocker in report.get("blockers") or ["None detected by audit."]]
    lines += ["", "## Full Audit JSON", "", "```json", safe_json_dumps(report), "```"]
    with open(os.path.abspath(path), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")

def _queue_from_leadgen(leadgen_id, graph_payload=None):
    existing = frappe.db.exists("Lead Intake Queue", {"source_lead_id": leadgen_id}) if has_doctype("Lead Intake Queue") else None
    if existing:
        return existing
    payload = {"entry": [{"id": (graph_payload or {}).get("page_id"), "changes": [{"field": "leadgen", "value": {"leadgen_id": leadgen_id, "page_id": (graph_payload or {}).get("page_id"), "form_id": (graph_payload or {}).get("form_id"), "created_time": (graph_payload or {}).get("created_time")}}]}]}
    event = _create_meta_event(payload, leadgen_id, graph_payload)
    doc = frappe.get_doc({"doctype": "Lead Intake Queue", "status": "Lead Received", "lead_source": "Meta Instant Form", "source_lead_id": leadgen_id, "raw_payload": safe_json_dumps({"source_lead_id": leadgen_id, "leadgen_id": leadgen_id, "event_type": "leadgen", "payload": payload, "value": {"leadgen_id": leadgen_id}, "change": {"field": "leadgen"}})})
    for field, value in {"event_type": "leadgen", "page_id": (graph_payload or {}).get("page_id"), "form_id": (graph_payload or {}).get("form_id"), "meta_webhook_event": event}.items():
        if has_field("Lead Intake Queue", field):
            doc.set(field, value)
    doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
    if event:
        _safe_set("Meta Webhook Event", event, {"queue": doc.name, "queue_status": "Lead Received"})
    frappe.db.commit()
    return doc.name

def _create_meta_event(payload, leadgen_id, graph_payload=None):
    if not has_doctype("Meta Webhook Event"):
        return None
    doc = frappe.new_doc("Meta Webhook Event")
    values = {"event_type": "leadgen", "leadgen_id": leadgen_id, "page_id": (graph_payload or {}).get("page_id"), "form_id": (graph_payload or {}).get("form_id"), "received_at": now(), "status": "Manual Download", "raw_json": safe_json_dumps(payload), "graph_api_response": safe_json_dumps(graph_payload or {})}
    for field, value in values.items():
        if doc.meta.has_field(field):
            doc.set(field, value)
    doc.insert(ignore_permissions=True)
    return doc.name

def _pipeline_row(queue_name):
    if not queue_name or not has_doctype("Lead Intake Queue"):
        return {}
    fields = ["name", "status", "creation", "modified"] + [f for f in ("source_lead_id", "retry_count", "last_error", "processing_started_at", "processing_completed_at", "graph_payload", "graph_api_request", "graph_api_response", "matched_lead", "matched_customer", "communication_event", "followup_reference", "meta_webhook_event") if has_field("Lead Intake Queue", f)]
    row = frappe.db.get_value("Lead Intake Queue", queue_name, fields, as_dict=True) or {}
    lead = row.get("matched_lead")
    customer = row.get("matched_customer")
    visa = _latest_linked("Visa Application", {"lead": lead} if lead and has_field("Visa Application", "lead") else ({"customer": customer} if customer and has_field("Visa Application", "customer") else None))
    data = {"queue": queue_name, "status": row.get("status"), "leadgen_id": row.get("source_lead_id"), "retry_count": row.get("retry_count"), "last_error": row.get("last_error"), "graph_request": load_json(row.get("graph_api_request"), {}) if row.get("graph_api_request") else None, "graph_response": load_json(row.get("graph_api_response"), {}) if row.get("graph_api_response") else None, "lead": lead, "customer": customer, "visa_application": visa, "communication_event": row.get("communication_event"), "followup": row.get("followup_reference"), "created": row.get("creation"), "modified": row.get("modified"), "processing_time": _processing_time(row)}
    if row.get("meta_webhook_event"):
        _safe_set("Meta Webhook Event", row.get("meta_webhook_event"), {"crm_lead": lead, "customer": customer, "visa_application": visa, "communication_event": row.get("communication_event")})
    return data

def _timeline(queue_name):
    row = _pipeline_row(queue_name)
    stages = [("Webhook", bool(queue_name), row.get("created")), ("Queue", bool(queue_name), row.get("created")), ("Graph", row.get("status") in ("Lead Downloaded", "Customer Matched", "Lead Created", "Processed") or bool(row.get("lead")), row.get("modified")), ("Customer360", bool(row.get("customer") or row.get("lead")), row.get("modified")), ("CRM Lead", bool(row.get("lead")), row.get("modified")), ("Visa", bool(row.get("visa_application")), row.get("modified")), ("Communication", bool(row.get("communication_event")), row.get("modified")), ("AI", False, None)]
    row["timeline"] = [{"stage": name, "state": "green" if ok else "yellow", "timestamp": ts} for name, ok, ts in stages]
    return row

def _ensure_visa_application(row):
    lead = row.get("lead") if row else None
    if not lead or row.get("visa_application"):
        return None
    try:
        from visa_crm.api.visa_application import create_for_lead
        return create_for_lead(lead)
    except Exception:
        return None

def _latest_linked(doctype, filters):
    if not filters or not has_doctype(doctype):
        return None
    rows = frappe.get_all(doctype, filters=filters, pluck="name", order_by="modified desc", limit=1)
    return rows[0] if rows else None

def _processing_time(row):
    start = row.get("processing_started_at") or row.get("creation")
    end = row.get("processing_completed_at") or row.get("modified")
    try:
        return round((frappe.utils.get_datetime(end) - frappe.utils.get_datetime(start)).total_seconds(), 2) if start and end else None
    except Exception:
        return None

def _parsed_payload(payload):
    out = []
    for entry in (payload or {}).get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            out.append({"field": change.get("field"), "entry_id": entry.get("id"), "leadgen_id": value.get("leadgen_id"), "page_id": value.get("page_id") or entry.get("id"), "form_id": value.get("form_id")})
    return out

def _safe_set(doctype, name, values):
    clean = {field: value for field, value in values.items() if value is not None and has_field(doctype, field)}
    if clean:
        frappe.db.set_value(doctype, name, clean, update_modified=False)
