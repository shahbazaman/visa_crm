import frappe
import requests
from frappe.utils import now
from visa_crm.api.meta_utils import (
    get_meta_settings,
    has_doctype,
    has_field,
    log_info,
    meta_debug_log,
    safe_json_dumps,
    redact_meta_tokens
)
from visa_crm.api.meta_graph import _access_token, _page_access_token, MetaGraphError


def get_configured_access_token():
    """Retrieve the decrypted Meta System User / Page access token from Meta Settings."""
    settings = get_meta_settings()
    if not settings:
        return None, None
    token = _page_access_token(settings) or _access_token(settings)
    page_id = getattr(settings, "page_id", None)
    return token, page_id


@frappe.whitelist()
def subscribe_page_webhooks():
    """
    Subscribes the Facebook Page to the Meta App so live webhooks are guaranteed to fire
    when new leads are submitted on Facebook Lead Forms.
    """
    token, page_id = get_configured_access_token()
    if not token or not page_id:
        return {"ok": False, "error": "Meta access token or Page ID not configured in Meta Settings"}

    url = f"https://graph.facebook.com/v21.0/{page_id}/subscribed_apps"
    params = {
        "subscribed_fields": "leadgen",
        "access_token": token
    }

    try:
        response = requests.post(url, data=params, timeout=10)
        res_json = response.json() if response.content else {}
        if response.status_code == 200 and res_json.get("success"):
            log_info("meta_page_subscribed_success", page_id=page_id)
            return {"ok": True, "page_id": page_id, "result": res_json}
        else:
            err_msg = redact_meta_tokens(str(res_json.get("error") or res_json))
            log_info("meta_page_subscribe_failed", page_id=page_id, error=err_msg)
            return {"ok": False, "page_id": page_id, "error": err_msg}
    except Exception as exc:
        err_msg = redact_meta_tokens(str(exc))
        log_info("meta_page_subscribe_exception", page_id=page_id, error=err_msg)
        return {"ok": False, "page_id": page_id, "error": err_msg}


@frappe.whitelist()
def get_page_lead_forms():
    """
    Fetches all Lead Forms associated with the configured Facebook Page.
    Returns list of dicts with 'id', 'name', 'status'.
    """
    token, page_id = get_configured_access_token()
    if not token or not page_id:
        return []

    settings = get_meta_settings()
    configured_form_ids = []
    if settings and getattr(settings, "lead_form_ids", None):
        raw_ids = str(settings.lead_form_ids).replace(",", "\n").splitlines()
        configured_form_ids = [fid.strip() for fid in raw_ids if fid.strip()]

    url = f"https://graph.facebook.com/v21.0/{page_id}/leadgen_forms"
    params = {
        "access_token": token,
        "fields": "id,name,status,leads_count,created_time",
        "limit": 50
    }

    forms = []
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json().get("data", [])
            for f in data:
                forms.append({
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "status": f.get("status"),
                    "leads_count": f.get("leads_count")
                })
    except Exception as exc:
        log_info("meta_fetch_forms_error", error=redact_meta_tokens(str(exc)))

    existing_ids = {f["id"] for f in forms}
    for cid in configured_form_ids:
        if cid not in existing_ids:
            forms.append({"id": cid, "name": f"Configured Form {cid}", "status": "ACTIVE"})

    return forms


@frappe.whitelist()
def fetch_form_leads(form_id, limit=50):
    """
    Fetches the latest leads directly from a specific Meta Lead Form via Graph API.
    """
    token, _ = get_configured_access_token()
    if not token or not form_id:
        return []

    url = f"https://graph.facebook.com/v21.0/{form_id}/leads"
    params = {
        "access_token": token,
        "fields": "id,created_time,field_data,ad_id,ad_name,adset_id,adset_name,campaign_id,campaign_name,form_id",
        "limit": int(limit or 50)
    }

    try:
        response = requests.get(url, params=params, timeout=12)
        if response.status_code == 200:
            return response.json().get("data", [])
        else:
            log_info("meta_fetch_leads_failed", form_id=form_id, status=response.status_code, error=redact_meta_tokens(response.text))
            return []
    except Exception as exc:
        log_info("meta_fetch_leads_exception", form_id=form_id, error=redact_meta_tokens(str(exc)))
        return []


@frappe.whitelist()
def sync_all_meta_leads(limit_per_form=50):
    """
    Main active synchronization method:
    1. Scans all active Lead Forms on the Facebook Page.
    2. Fetches latest leads directly via Graph API.
    3. Detects any leads not yet in Lead Intake Queue.
    4. Automatically ingests, downloads, normalizes, and processes them through the full pipeline.
    """
    token, page_id = get_configured_access_token()
    if not token:
        return {"ok": False, "error": "Meta access token not configured"}

    forms = get_page_lead_forms()
    if not forms:
        return {"ok": False, "message": "No active lead forms found on Meta Page"}

    from visa_crm.api.intake_processor import process_queue
    from visa_crm.api.meta_webhook import _insert_queue, _lead_source

    total_synced = 0
    newly_created = []
    already_existing = 0

    for form in forms:
        form_id = form.get("id")
        if not form_id:
            continue
        leads = fetch_form_leads(form_id, limit=limit_per_form)
        for lead_item in leads:
            lead_id = str(lead_item.get("id") or "").strip()
            if not lead_id or lead_id.lower() in ("none", "null", ""):
                continue

            existing_queue = frappe.db.exists("Lead Intake Queue", {"source_lead_id": lead_id}) or frappe.db.get_value("Lead Intake Queue", {"source_lead_id": str(lead_id).strip()}, "name")
            if existing_queue:
                already_existing += 1
                q_status = frappe.db.get_value("Lead Intake Queue", existing_queue, "status")
                if q_status in ("Lead Received", "Pending Processing", "Action Required", "Needs Retry"):
                    try:
                        process_queue(existing_queue)
                        frappe.db.commit()
                    except Exception:
                        pass
                continue

            item_payload = {
                "event_type": "leadgen",
                "entry_id": page_id,
                "source_lead_id": lead_id,
                "leadgen_id": lead_id,
                "page_id": page_id,
                "form_id": form_id,
                "received_at": now(),
                "graph_lead_data": lead_item
            }

            queue_name, created = _insert_queue(item_payload, event_log=None)
            frappe.db.commit()

            if created:
                total_synced += 1
                newly_created.append(queue_name)
                try:
                    process_queue(queue_name)
                    frappe.db.commit()
                except Exception as exc:
                    log_info("meta_poll_process_failed", queue=queue_name, error=redact_meta_tokens(str(exc)))

    return {
        "ok": True,
        "forms_checked": len(forms),
        "newly_synced_leads": total_synced,
        "already_existing_leads": already_existing,
        "new_queues": newly_created
    }


@frappe.whitelist()
def poll_meta_leads_cron():
    """
    Scheduled cron job executed every minute to guarantee all new Meta leads
    are retrieved and processed even if webhooks are delayed.
    """
    try:
        return sync_all_meta_leads(limit_per_form=25)
    except Exception as exc:
        log_info("meta_poll_cron_error", error=redact_meta_tokens(str(exc)))
        return {"ok": False, "error": redact_meta_tokens(str(exc))}
