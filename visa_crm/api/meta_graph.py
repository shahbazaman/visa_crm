import requests
import frappe
from visa_crm.api.meta_utils import get_meta_settings, log_info, meta_debug_log, safe_json_dumps

GRAPH_VERSION = "v20.0"
LEAD_FIELDS = "id,created_time,field_data,form_id,page_id,ad_id,ad_name,adset_id,adset_name,campaign_id,campaign_name"

class MetaGraphError(Exception):
    def __init__(self, message, request=None, response=None, status_code=None):
        super().__init__(message)
        self.request = request or {}
        self.response = response
        self.status_code = status_code

def fetch_lead(leadgen_id, settings=None, context=None):
    context = context or {}
    ctx = {k: v for k, v in context.items() if k != "source_lead_id"}
    meta_debug_log("fetch_lead_start", source_lead_id=leadgen_id, **ctx)
    settings = settings or get_meta_settings()
    token = _access_token(settings)
    if not token:
        meta_debug_log("fetch_lead_exception", source_lead_id=leadgen_id, error="Meta Page Access Token is not configured", **ctx)
        raise MetaGraphError("Meta Page Access Token is not configured")
    try:
        lead = _get(f"{leadgen_id}", {"fields": LEAD_FIELDS, "access_token": token})
        _hydrate_names(lead, token)
        log_info("meta_graph_lead_fetched", leadgen_id=leadgen_id)
        meta_debug_log("fetch_lead_end", source_lead_id=leadgen_id, graph_id=lead.get("id"), **ctx)
        return lead
    except MetaGraphError as exc:
        meta_debug_log("fetch_lead_exception", source_lead_id=leadgen_id, error=str(exc), status_code=exc.status_code, graph_response=exc.response, graph_request=exc.request, **ctx)
        raise
    except Exception:
        meta_debug_log("fetch_lead_exception", source_lead_id=leadgen_id, traceback=frappe.get_traceback(), **ctx)
        raise

def _get(path, params):
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{path}"
    request = {"url": url, "path": path, "params": {k: v for k, v in (params or {}).items() if k != "access_token"}}
    try:
        response = requests.get(url, params=params, timeout=20)
    except requests.RequestException as exc:
        raise MetaGraphError(str(exc), request=request) from exc
    data = _response_json(response)
    if response.status_code >= 400:
        if isinstance(data, dict):
            data["status_code"] = response.status_code
        error = data.get("error", {}) if isinstance(data, dict) else {}
        if isinstance(error, dict):
            error["http_status"] = response.status_code
        message = error.get("message") or f"Graph API HTTP {response.status_code}"
        raise MetaGraphError(message, request=request, response=data, status_code=response.status_code)
    meta_debug_log("meta_graph_response", source_lead_id=path, status_code=response.status_code, graph_response=data, graph_request=request)
    return data

def _response_json(response):
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw_response": response.text[:5000]}

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
