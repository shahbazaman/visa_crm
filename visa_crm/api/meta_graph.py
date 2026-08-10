import requests
import frappe
from visa_crm.api.meta_utils import get_meta_settings, log_info, meta_debug_log, safe_json_dumps

GRAPH_VERSION = "v20.0"
LEAD_FIELDS = "id,created_time,field_data,form_id,ad_id,ad_name,adset_id,adset_name,campaign_id,campaign_name"

class MetaGraphError(Exception):
    def __init__(self, message, request=None, response=None, status_code=None):
        super().__init__(message)
        self.request = request or {}
        self.response = response
        self.status_code = status_code

def fetch_lead(leadgen_id, settings=None, context=None):
    context = context or {}
    ctx = {k: v for k, v in context.items() if k != "source_lead_id"}
    if not leadgen_id or str(leadgen_id).strip().lower() in ("none", "null", "0", ""):
        meta_debug_log("fetch_lead_exception", source_lead_id=leadgen_id, error="GRAPH_DOWNLOAD cannot execute: Meta leadgen ID is missing or invalid", **ctx)
        raise MetaGraphError("GRAPH_DOWNLOAD cannot execute: Meta leadgen ID is missing or invalid")
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
    if not isinstance(lead, dict):
        return
    for key, field in {"campaign_id": "campaign_name", "adset_id": "adset_name", "ad_id": "ad_name"}.items():
        val = lead.get(key)
        if lead.get(field) or not val or str(val).strip().lower() in ("none", "null", "0", ""):
            continue
        try:
            name_resp = _get(str(val), {"fields": "name", "access_token": token})
            if isinstance(name_resp, dict) and name_resp.get("name"):
                lead[field] = name_resp.get("name")
        except MetaGraphError:
            log_info("meta_graph_context_name_missing", id=val, field=field)

def _access_token(settings):
    if not settings:
        return None
    for field in ("access_token", "page_access_token", "facebook_page_access_token", "meta_page_access_token"):
        token = _password_or_value(settings, field)
        if token:
            return token
    for key in ("meta_page_access_token", "facebook_page_access_token", "page_access_token"):
        token = frappe.conf.get(key)
        if token:
            return token
    return None

def _password_or_value(settings, fieldname):
    try:
        token = settings.get_password(fieldname, raise_exception=False)
        if token:
            return token
    except Exception:
        pass
    return getattr(settings, fieldname, None)

def _secret(settings):
    return _password_or_value(settings, "meta_app_secret") or frappe.conf.get("meta_app_secret")

def check_page_subscription(settings=None):
    settings = settings or get_meta_settings()
    page_id = getattr(settings, "page_id", None) if settings else None
    token = _access_token(settings)
    app_id = getattr(settings, "meta_app_id", None) if settings else None
    app_secret = _secret(settings)
    if not page_id or not token:
        return {"ok": False, "error": "Missing page_id or access_token in Meta Settings"}
    try:
        data = None
        last_exc = None
        for tok in filter(None, [token, f"{app_id}|{app_secret}" if app_id and app_secret else None]):
            try:
                res = _get(f"{page_id}/subscribed_apps", {"access_token": tok})
                if isinstance(res, dict) and "data" in res:
                    data = res
                    break
            except Exception as exc:
                last_exc = exc
        if not data:
            if last_exc:
                raise last_exc
            data = _get(f"{page_id}/subscribed_apps", {"access_token": token})
        apps = data.get("data", []) if isinstance(data, dict) else []
        subscribed = any(
            (app_id and str(app.get("id")) == str(app_id)) or "leadgen" in (app.get("subscribed_fields") or [])
            for app in apps
        )
        return {
            "ok": True,
            "page_id": page_id,
            "apps": apps,
            "is_subscribed": subscribed
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def subscribe_page_leadgen(settings=None):
    settings = settings or get_meta_settings()
    page_id = getattr(settings, "page_id", None) if settings else None
    token = _access_token(settings)
    if not page_id or not token:
        return {"ok": False, "error": "Missing page_id or access_token in Meta Settings"}
    try:
        url = f"https://graph.facebook.com/{GRAPH_VERSION}/{page_id}/subscribed_apps"
        resp = requests.post(url, data={"subscribed_fields": "leadgen", "access_token": token}, timeout=20)
        data = _response_json(resp)
        is_ok = bool(resp.status_code == 200 and data and data.get("success") is True)
        log_info("subscribe_page_leadgen", page_id=page_id, ok=is_ok, response=data)
        return {"ok": is_ok, "response": data, "status_code": resp.status_code}
    except Exception as exc:
        log_info("subscribe_page_leadgen_failed", page_id=page_id, error=str(exc))
        return {"ok": False, "error": str(exc)}
