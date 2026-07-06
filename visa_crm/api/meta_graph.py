import requests
import frappe
from visa_crm.api.meta_utils import get_meta_settings, log_info, meta_debug_log

GRAPH_VERSION = "v20.0"
LEAD_FIELDS = "id,created_time,field_data,form_id,page_id,ad_id,ad_name,adset_id,adset_name,campaign_id,campaign_name"

class MetaGraphError(Exception):
    pass

def fetch_lead(leadgen_id, settings=None, context=None):
    context = context or {}
    ctx = {k: v for k, v in context.items() if k != "source_lead_id"}
    meta_debug_log("fetch_lead_start", source_lead_id=leadgen_id, **ctx)
    settings = settings or get_meta_settings()
    token = _access_token(settings)
    if not token:
        meta_debug_log("fetch_lead_exception", source_lead_id=leadgen_id, traceback=frappe.get_traceback(), **ctx)
        raise MetaGraphError("Meta Page Access Token is not configured")
    try:
        lead = _get(f"{leadgen_id}", {"fields": LEAD_FIELDS, "access_token": token})
        _hydrate_names(lead, token)
        log_info("meta_graph_lead_fetched", leadgen_id=leadgen_id)
        meta_debug_log("fetch_lead_end", source_lead_id=leadgen_id, graph_id=lead.get("id"), **ctx)
        return lead
    except Exception:
        meta_debug_log("fetch_lead_exception", source_lead_id=leadgen_id, traceback=frappe.get_traceback(), **ctx)
        raise

def _get(path, params):
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{path}"
    try:
        response = requests.get(url, params=params, timeout=20)
    except requests.RequestException as exc:
        raise MetaGraphError(str(exc)) from exc
    data = response.json() if response.content else {}
    if response.status_code >= 400:
        error = data.get("error", {}) if isinstance(data, dict) else {}
        raise MetaGraphError(error.get("message") or f"Graph API HTTP {response.status_code}")
    return data

def _hydrate_names(lead, token):
    for key, field in {"campaign_id": "campaign_name", "adset_id": "adset_name", "ad_id": "ad_name"}.items():
        if lead.get(field) or not lead.get(key):
            continue
        try:
            lead[field] = _get(lead.get(key), {"fields": "name", "access_token": token}).get("name")
        except MetaGraphError:
            log_info("meta_graph_context_name_missing", id=lead.get(key), field=field)

def _access_token(settings):
    if not settings:
        return None
    return settings.get_password("access_token") or getattr(settings, "access_token", None)
