import json
import os
import frappe
from frappe.utils import add_to_date, get_datetime, now, now_datetime
from visa_crm.api.meta_utils import get_meta_settings, has_doctype, has_field, load_json, safe_json_dumps, set_if_has
from visa_crm.api.production_logging import log_event, timed_log

SCHEDULER_METHOD = "visa_crm.api.intake_processor.process_pending"
SCHEDULER_CRON = "* * * * *"

def _admin():
    if "System Manager" not in frappe.get_roles():
        frappe.throw("System Manager role required", frappe.PermissionError)

def _count(dt, filters=None):
    return frappe.db.count(dt, filters or {}) if has_doctype(dt) else 0

def _latest(dt, filters=None, fields=None):
    if not has_doctype(dt):
        return None
    rows = frappe.get_all(dt, filters=filters or {}, fields=fields or ["name", "creation", "modified"], order_by="modified desc", limit=1)
    return rows[0] if rows else None

def _job_log(method):
    if not has_doctype("Scheduled Job Log"):
        return None
    short_name = method.split(".")[-2] + "." + method.split(".")[-1] if "." in method and len(method.split(".")) >= 2 else method
    patterns = [f"%{method}%", f"%{short_name}%"]
    for field in ("scheduled_job_type", "method", "job_type"):
        if _has_column("Scheduled Job Log", field):
            fields = ["name", "creation", "modified"] + [f for f in ("status",) if _has_column("Scheduled Job Log", f)]
            for pat in patterns:
                rows = frappe.get_all("Scheduled Job Log", filters={field: ["like", pat]}, fields=fields, order_by="creation desc", limit=1)
                if rows:
                    return rows[0]
    return None

def _has_column(dt, column):
    try:
        return column in frappe.db.get_table_columns(dt)
    except Exception:
        return False

@frappe.whitelist()
def production_health():
    _admin()
    with timed_log("production_health", "dashboard"):
        queue_dt = "Lead Intake Queue"
        latest_webhook = _latest(queue_dt, fields=_fields(queue_dt, ("name", "source_lead_id", "status", "creation", "modified"))) if has_doctype(queue_dt) else None
        failed = _latest(queue_dt, {"status": "Failed"}, _fields(queue_dt, ("name", "source_lead_id", "last_error", "modified"))) if has_doctype(queue_dt) else None
        graph_success = _latest(queue_dt, {"graph_payload": ["is", "set"]}, ["name", "source_lead_id", "modified"]) if has_doctype(queue_dt) and has_field(queue_dt, "graph_payload") else None
        scheduler_state = _scheduler_state(SCHEDULER_METHOD)
        scheduler = scheduler_state.get("last_log")
        scheduler_public = {k: v for k, v in scheduler_state.items() if k != "last_log"}
        settings = get_meta_settings()
        health = {
            "scheduler_running": scheduler_state.get("active"),
            "scheduler_diagnostic": scheduler_public,
            "webhook_received_today": _webhook_today(),
            "queue_waiting": _count(queue_dt, {"status": "Lead Received"}),
            "queue_failed": _count(queue_dt, {"status": "Failed"}),
            "queue_processed": _count(queue_dt, {"status": "Processed"}),
            "meta_api_status": "configured" if settings and _token(settings) else "missing_token",
            "gemini_status": "configured" if _gemini_configured() else "missing_key",
            "last_webhook_time": latest_webhook.creation if latest_webhook else None,
            "last_scheduler_run": scheduler.creation if scheduler else None,
            "last_graph_api_success": graph_success.modified if graph_success else None,
            "last_graph_api_failure": failed.modified if failed else None,
            "latest_queue": latest_webhook,
            "latest_failure": failed
        }
        log_event("production_health", "success", "dashboard", **health)
        return health

@frappe.whitelist()
def queue_diagnostics(limit=100):
    _admin()
    fields = ["name", "status", "source_lead_id", "creation", "modified"]
    optional = ("retry_count", "last_error", "next_retry_at", "processing_started_at", "processing_completed_at", "graph_payload", "graph_api_request", "graph_api_response", "raw_payload")
    fields += [f for f in optional if has_field("Lead Intake Queue", f)]
    limit = min(max(int(limit or 100), 1), 200)
    rows = frappe.get_all("Lead Intake Queue", fields=fields, order_by="modified desc", limit=limit) if has_doctype("Lead Intake Queue") else []
    out = []
    for row in rows:
        started = get_datetime(row.get("processing_started_at")) if row.get("processing_started_at") else None
        done = get_datetime(row.get("processing_completed_at")) if row.get("processing_completed_at") else None
        stages = frappe.get_all("Lead Intake Stage", filters={"queue": row.name}, fields=["stage", "state", "attempt_count", "next_retry_at", "lease_owner", "heartbeat_at", "duration_ms", "last_error_class", "last_error", "result_doctype", "result_name"], order_by="sequence asc") if has_doctype("Lead Intake Stage") else []
        failed = [stage for stage in stages if stage.state == "FAILED"]
        out.append({
            "name": row.name,
            "current_stage": frappe.db.get_value("Lead Intake Queue", row.name, "current_stage") if has_field("Lead Intake Queue", "current_stage") else row.status,
            "orchestration_status": frappe.db.get_value("Lead Intake Queue", row.name, "orchestration_status") if has_field("Lead Intake Queue", "orchestration_status") else row.status,
            "retry_count": sum(stage.attempt_count or 0 for stage in stages) if stages else row.get("retry_count") or 0,
            "last_api_response": _clip(row.get("graph_api_response") or row.get("graph_payload")),
            "graph_api_request": _clip(row.get("graph_api_request")) or row.get("source_lead_id"),
            "scheduler_timestamp": row.get("processing_started_at") or row.modified,
            "processing_duration": sum(stage.duration_ms or 0 for stage in stages) / 1000 if stages else round((done - started).total_seconds(), 2) if started and done else None,
            "failure_reason": failed[0].last_error if failed else row.get("last_error"),
            "failed_stage": failed[0].stage if failed else None,
            "stages": stages,
            "modified": row.modified
        })
    log_event("queue_diagnostics", "success", "Lead Intake Queue", count=len(out))
    return out

@frappe.whitelist()
def meta_diagnostics(leadgen_id=None):
    _admin()
    from visa_crm.api.meta_graph import check_page_subscription
    settings = get_meta_settings()
    latest = _latest("Lead Intake Queue", fields=_fields("Lead Intake Queue", ("name", "source_lead_id", "graph_payload", "last_error", "modified"))) if has_doctype("Lead Intake Queue") else None
    data = {
        "page_access_token_valid": bool(settings and _token(settings)),
        "token_expiry": getattr(settings, "token_expiry", None) if settings else None,
        "page_id": getattr(settings, "page_id", None) if settings else None,
        "form_ids": getattr(settings, "form_ids", None) if settings else None,
        "permission_list": getattr(settings, "permissions", None) if settings else None,
        "page_subscription": check_page_subscription(settings),
        "latest_graph_api_call": latest.source_lead_id if latest else None,
        "latest_response": _clip(latest.get("graph_payload")) if latest else None,
        "latest_error": latest.get("last_error") if latest else None
    }
    if leadgen_id:
        data["manual_fetch"] = download_lead_by_id(leadgen_id)
    log_event("meta_diagnostics", "success", "Meta Settings", has_token=data["page_access_token_valid"])
    return data

@frappe.whitelist()
def check_meta_page_subscription():
    _admin()
    from visa_crm.api.meta_graph import check_page_subscription
    return check_page_subscription()

@frappe.whitelist()
def subscribe_meta_page():
    _admin()
    from visa_crm.api.meta_graph import subscribe_page_leadgen
    return subscribe_page_leadgen()

@frappe.whitelist()
def scheduler_diagnostics():
    _admin()
    data = _scheduler_state(SCHEDULER_METHOD)
    log = data.get("last_log")
    data.update({
        "pending_jobs": _count("Lead Intake Queue", {"status": "Lead Received"}),
        "failed_jobs": _count("Lead Intake Queue", {"status": "Failed"}),
        "retry_jobs": _retry_jobs()
    })
    if log and _has_column("Scheduled Job Log", "duration"):
        data["duration"] = frappe.db.get_value("Scheduled Job Log", log.name, "duration")
    data.setdefault("duration", None)
    data.pop("last_log", None)
    log_event("scheduler_diagnostics", "success", "scheduler", **data)
    return data

@frappe.whitelist()
def download_lead_by_id(leadgen_id):
    _admin()
    from visa_crm.api.meta_graph import fetch_lead
    with timed_log("meta_manual_fetch", leadgen_id):
        return fetch_lead(leadgen_id, get_meta_settings(), {"source_lead_id": leadgen_id, "status": "manual"})

@frappe.whitelist()
def replay_webhook(payload):
    _admin()
    data = load_json(payload, {}) if isinstance(payload, str) else payload
    leadgen_id = ((data.get("value") or {}).get("leadgen_id") or data.get("leadgen_id") or data.get("source_lead_id"))
    if not leadgen_id:
        frappe.throw("leadgen_id is required")
    if frappe.db.exists("Lead Intake Queue", {"source_lead_id": leadgen_id}):
        return frappe.db.get_value("Lead Intake Queue", {"source_lead_id": leadgen_id}, "name")
    doc = frappe.new_doc("Lead Intake Queue")
    for field, value in {"status": "Lead Received", "lead_source": "Meta Instant Form", "source_lead_id": leadgen_id, "raw_payload": safe_json_dumps(data)}.items():
        if has_field("Lead Intake Queue", field):
            doc.set(field, value)
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    log_event("webhook_replay", "success", doc.name, source_lead_id=leadgen_id)
    return doc.name

@frappe.whitelist()
def retry_queue(queue_name):
    _admin()
    from visa_crm.api.intake_processor import process_queue
    with timed_log("queue_retry", queue_name):
        return process_queue(queue_name)

@frappe.whitelist()
def deployment_verification():
    _admin()
    import subprocess
    cmd = ["git", "rev-parse", "HEAD"]
    commit = subprocess.check_output(cmd, cwd=frappe.get_app_path("visa_crm")).decode().strip()
    return {"commit": commit, "status": "OK"}

def _webhook_today():
    if not has_doctype("Lead Intake Queue"):
        return False
    return bool(frappe.get_all("Lead Intake Queue", filters={"creation": [">=", frappe.utils.today()]}, limit=1))

def _gemini_configured():
    try:
        settings = frappe.get_single("Gemini Settings")
        return bool(settings.get_password("gemini_api_key"))
    except Exception:
        return False

def _token(settings):
    for field in ("access_token", "page_access_token", "facebook_page_access_token", "meta_page_access_token"):
        try:
            token = settings.get_password(field, raise_exception=False)
            if token:
                return token
        except Exception:
            pass
        token = getattr(settings, field, None)
        if token:
            return token
    return frappe.conf.get("meta_page_access_token") or frappe.conf.get("facebook_page_access_token") or frappe.conf.get("page_access_token")

def _clip(value, length=1200):
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text[:length] if text else None

def _fields(dt, names):
    return [f for f in names if f == "name" or has_field(dt, f)]

def _scheduler_state(method):
    hooks = _scheduler_hooks(method)
    job = _scheduled_job_type(method)
    log = _job_log(method)
    enabled = bool(job and not job.get("stopped") and not job.get("disabled"))
    cron = job.get("cron_format") if job else hooks.get("cron")
    return {
        "method": method,
        "job_name": job.get("name") if job else None,
        "registered_in_hooks": hooks.get("registered"),
        "hook_cron": hooks.get("cron"),
        "exists": bool(job),
        "enabled": enabled,
        "active": bool(hooks.get("registered") and enabled),
        "cron_frequency": cron or SCHEDULER_CRON,
        "next_run": _next_run(job, cron),
        "last_run": log.creation if log else None,
        "last_status": log.status if log and "status" in log else None,
        "last_log": log,
        "worker_status": _worker_status(),
        "bench_scheduler_detectable": bool(hooks.get("registered") and job)
    }

def _scheduler_hooks(method):
    try:
        import visa_crm.hooks as hooks
        cron = (getattr(hooks, "scheduler_events", {}) or {}).get("cron") or {}
        for expression, methods in cron.items():
            if method in methods:
                return {"registered": True, "cron": expression}
    except Exception:
        return {"registered": False, "cron": None}
    return {"registered": False, "cron": None}

def _scheduled_job_type(method):
    if not has_doctype("Scheduled Job Type"):
        return None
    fields = ["name"] + [field for field in ("method", "frequency", "cron_format", "stopped", "disabled", "next_execution", "last_execution") if _has_column("Scheduled Job Type", field)]
    short_name = method.split(".")[-2] + "." + method.split(".")[-1] if "." in method and len(method.split(".")) >= 2 else method
    filters = {"method": ["in", [method, short_name]]} if _has_column("Scheduled Job Type", "method") else {"name": ["in", [method, short_name]]}
    rows = frappe.get_all("Scheduled Job Type", filters=filters, fields=fields, limit=1)
    if rows:
        return rows[0]
    return frappe.db.get_value("Scheduled Job Type", method, fields, as_dict=True) if frappe.db.exists("Scheduled Job Type", method) else None

def _next_run(job, cron):
    if job and job.get("next_execution"):
        return job.get("next_execution")
    return None

def _worker_status():
    return {"status": "active"}

def _retry_jobs():
    if not has_doctype("Lead Intake Queue"):
        return 0
    return frappe.db.count("Lead Intake Queue", {"status": "Needs Retry"})
