import requests
import frappe
from visa_crm.api.meta_utils import get_meta_settings, log_info, meta_debug_log, safe_json_dumps

GRAPH_VERSION = "v21.0"
LEAD_FIELDS = "id,created_time,field_data,form_id,ad_id,ad_name,adset_id,adset_name,campaign_id,campaign_name"

class MetaGraphError(Exception):
    permanent = False
    def __init__(self, message, request=None, response=None, status_code=None):
        super().__init__(message)
        self.request = request or {}
        self.response = response
        self.status_code = status_code

class PermanentGraphError(MetaGraphError):
    """Non-retryable Graph API error (e.g., object does not exist, invalid ID, revoked token)."""
    permanent = True

# Prefixes that indicate a synthetic/internal ID — never a real Meta leadgen ID.
# This follows the same convention as intake_processor._ignored_test_event().
# Real Meta leadgen IDs are always numeric strings of ≥13 digits.
_SYNTHETIC_ID_PREFIXES = ("attr-", "manual-", "test-", "synthetic-", "dummy-", "fake-")


def is_synthetic_leadgen_id(leadgen_id):
    """Return True when *leadgen_id* is clearly not a real Meta leadgen ID.

    Real Meta leadgen IDs are always large decimal integers (≥ 13 digits).
    Internal CRM attribution records, test harnesses and built-in CRM sync
    produce identifiers such as ``ATTR-4aafda9a``, ``manual-...`` etc.
    These must never be sent to the Meta Graph API as a leadgen object path.
    """
    if not leadgen_id:
        return False
    s = str(leadgen_id).strip().lower()
    if any(s.startswith(p) for p in _SYNTHETIC_ID_PREFIXES):
        return True
    # A real Meta leadgen ID is a large pure-decimal number (≥ 13 digits).
    if s.isdigit() and len(s) >= 13:
        return False
    # Anything else — non-numeric IDs, short numeric IDs, hex strings — is synthetic.
    return True


def fetch_lead(leadgen_id, settings=None, context=None):
    if not leadgen_id or str(leadgen_id).strip().lower() in ("none", "null", "0", ""):
        context = context or {}
        ctx = {k: v for k, v in context.items() if k != "source_lead_id"}
        meta_debug_log("fetch_lead_exception", source_lead_id=leadgen_id, error="GRAPH_DOWNLOAD cannot execute: Meta leadgen ID is missing or invalid", **ctx)
        raise PermanentGraphError("GRAPH_DOWNLOAD cannot execute: Meta leadgen ID is missing or invalid")

    leadgen_str = str(leadgen_id).strip()
    assert isinstance(leadgen_str, str), "source_lead_id must be string"
    assert leadgen_str and leadgen_str.lower() not in ("none", "null", "0", ""), "source_lead_id cannot be blank or None"

    # Guard: synthetic / internal IDs must never reach the Meta Graph API.
    if is_synthetic_leadgen_id(leadgen_str):
        context = context or {}
        ctx = {k: v for k, v in context.items() if k != "source_lead_id"}
        msg = (f"GRAPH_DOWNLOAD cannot execute: source_lead_id '{leadgen_str}' is a synthetic/internal "
               f"identifier and is not a valid Meta leadgen ID. "
               f"This record should be ignored rather than retried.")
        meta_debug_log("fetch_lead_exception", source_lead_id=leadgen_str, error=msg, **ctx)
        raise PermanentGraphError(msg)

    context = context or {}
    ctx = {k: v for k, v in context.items() if k != "source_lead_id"}
    meta_debug_log("fetch_lead_start", source_lead_id=leadgen_str, endpoint=f"https://graph.facebook.com/{GRAPH_VERSION}/{leadgen_str}", **ctx)
    settings = settings or get_meta_settings()
    token = _access_token(settings)
    if not token:
        meta_debug_log("fetch_lead_exception", source_lead_id=leadgen_str, error="Meta Page Access Token is not configured", **ctx)
        raise MetaGraphError("Meta Page Access Token is not configured")
    try:
        lead = _get(f"{leadgen_str}", {"fields": LEAD_FIELDS, "access_token": token})
        # Optional enrichment: resolve human-readable campaign/ad names.
        # Failures here MUST NOT affect the primary lead payload or error state.
        enrichment_warnings = _hydrate_names(lead, token)
        if enrichment_warnings:
            lead.setdefault("_enrichment_warnings", [])
            lead["_enrichment_warnings"].extend(enrichment_warnings)
        log_info("meta_graph_lead_fetched", leadgen_id=leadgen_str)
        meta_debug_log("fetch_lead_end", source_lead_id=leadgen_str, graph_id=lead.get("id"),
                       enrichment_warnings=enrichment_warnings or [], **ctx)
        return lead
    except MetaGraphError as exc:
        meta_debug_log("fetch_lead_exception", source_lead_id=leadgen_str, error=str(exc), status_code=exc.status_code, graph_response=exc.response, graph_request=exc.request, **ctx)
        raise
    except Exception:
        meta_debug_log("fetch_lead_exception", source_lead_id=leadgen_str, traceback=frappe.get_traceback(), **ctx)
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
        raw_msg = error.get("message") or f"Graph API HTTP {response.status_code}"
        err_code = error.get("code")
        err_subcode = error.get("error_subcode") or error.get("subcode")
        if "Object with ID" in raw_msg and "None" in raw_msg:
            message = f"Meta Graph API Permission Error ({raw_msg}): Page Access Token lacks 'leads_retrieval' permission or leadgen ID {path} belongs to a different Page/App."
        elif err_code == 100 and "nonexisting field" in raw_msg:
            message = f"Meta Graph API Permission Error ({raw_msg}): Page Access Token lacks 'leads_retrieval' permission."
        else:
            message = raw_msg
        meta_debug_log("meta_graph_error", path=path, status_code=response.status_code, error=message, graph_request=request, graph_response=data)
        # Classify permanent (non-retryable) errors:
        # 100/33: object does not exist; 190: invalid/expired token; 4: rate limit (retryable)
        is_permanent = (
            (err_code == 100 and err_subcode in (33, 100)) or  # object not found / nonexistent field
            (err_code == 100 and "nonexisting field" in raw_msg) or
            err_code == 190 or  # invalid/expired OAuth token
            response.status_code == 400 and err_subcode == 33  # explicit object-not-found
        )
        exc_class = PermanentGraphError if is_permanent else MetaGraphError
        raise exc_class(message, request=request, response=data, status_code=response.status_code)
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
    """Resolve human-readable campaign/adset/ad names from their IDs.

    This is optional metadata enrichment.  Failures here are non-fatal and
    must not affect the primary lead payload or propagate as Graph errors.

    Returns a list of warning dicts (possibly empty) describing any lookup
    failures so callers can log/store them without polluting error fields.
    """
    warnings = []
    if not isinstance(lead, dict):
        return warnings
    for key, field in {"campaign_id": "campaign_name", "adset_id": "adset_name", "ad_id": "ad_name"}.items():
        val = lead.get(key)
        if lead.get(field) or not val or str(val).strip().lower() in ("none", "null", "0", ""):
            continue
        # Synthetic IDs cannot be looked up — skip silently.
        if is_synthetic_leadgen_id(str(val)):
            warnings.append({"field": key, "id": val, "reason": "synthetic_id_skipped"})
            log_info("meta_graph_enrichment_skipped", id=val, field=field, reason="synthetic_id")
            continue
        try:
            name_resp = _get(str(val), {"fields": "name", "access_token": token})
            if isinstance(name_resp, dict) and name_resp.get("name"):
                lead[field] = name_resp.get("name")
        except MetaGraphError as exc:
            # Optional enrichment failure — log but do NOT re-raise.
            warnings.append({"field": key, "id": val, "reason": "lookup_failed", "error": str(exc)})
            log_info("meta_graph_context_name_missing", id=val, field=field, error=str(exc))
    return warnings

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

@frappe.whitelist()
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
        for tok in filter(None, [token, f"{app_id}|{app_secret}" if app_id and app_secret else None]):
            try:
                res = _get(f"{page_id}/subscribed_apps", {"access_token": tok})
                if isinstance(res, dict) and "data" in res:
                    data = res
                    break
            except Exception:
                pass
        if data:
            apps = data.get("data", []) if isinstance(data, dict) else []
            subscribed = any(
                (app_id and str(app.get("id")) == str(app_id)) or "leadgen" in (app.get("subscribed_fields") or [])
                for app in apps
            )
            return {"ok": True, "page_id": page_id, "apps": apps, "is_subscribed": subscribed}

        sub_res = subscribe_page_leadgen(settings)
        if sub_res.get("ok") or (sub_res.get("response") or {}).get("success") is True:
            return {
                "ok": True,
                "page_id": page_id,
                "apps": [{"id": app_id, "subscribed_fields": ["leadgen"]}],
                "is_subscribed": True
            }
        err_msg = sub_res.get("error") or safe_json_dumps(sub_res.get("response"))
        return {"ok": False, "error": f"Page subscription POST failed: {err_msg}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _page_access_token(settings=None):
    settings = settings or get_meta_settings()
    token = _access_token(settings)
    page_id = getattr(settings, "page_id", None) if settings else None
    if not token or not page_id:
        return token
    try:
        resp = requests.get(f"https://graph.facebook.com/{GRAPH_VERSION}/{page_id}", params={"fields": "access_token", "access_token": token}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and data.get("access_token"):
                return data.get("access_token")
    except Exception:
        pass
    return token

@frappe.whitelist()
def subscribe_page_leadgen(settings=None):
    settings = settings or get_meta_settings()
    page_id = getattr(settings, "page_id", None) if settings else None
    token = _page_access_token(settings) or _access_token(settings)
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


@frappe.whitelist()
def debug_meta_token():
    """Debugs the current token against Meta Graph API /debug_token to inspect scopes and expiry."""
    settings = get_meta_settings()
    token = _access_token(settings)
    app_id = getattr(settings, "meta_app_id", None) if settings else None
    app_secret = _secret(settings)
    if not token:
        return {"ok": False, "error": "No access token configured"}

    app_token = f"{app_id}|{app_secret}" if app_id and app_secret else token
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/debug_token"
    params = {
        "input_token": token,
        "access_token": app_token
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        return {"ok": resp.status_code == 200, "status_code": resp.status_code, "data": resp.json().get("data", resp.json())}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
