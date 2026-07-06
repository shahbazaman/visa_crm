import frappe
from visa_crm.api.meta_utils import load_json, meta_debug_log, normalize_phone

DEFAULT_FIELD_MAP = {
    "customer_name": ["full_name", "name", "first_name", "last_name"],
    "phone": ["phone_number", "phone", "mobile", "mobile_number"],
    "email": ["email", "email_address"],
    "country_interested": ["country", "country_interested", "destination_country", "preferred_country"],
    "visa_type": ["visa_type", "visa_category", "type_of_visa"],
    "whatsapp": ["whatsapp", "whatsapp_number", "wa_number"]
}

def normalize_lead(graph_payload, settings=None, context=None):
    context = context or {}
    meta_debug_log("normalize_lead_start", **context)
    try:
        answers = _answers(graph_payload)
        mapping = _mapping(settings)
        data = {field: _first_value(answers, keys) for field, keys in mapping.items()}
        if not data.get("customer_name"):
            data["customer_name"] = " ".join(filter(None, [answers.get("first_name"), answers.get("last_name")])) or None
        data["phone"] = normalize_phone(data.get("phone"))
        data["whatsapp"] = normalize_phone(data.get("whatsapp"))
        data["email"] = (data.get("email") or "").strip().lower() or None
        for target, source in {"campaign_name": "campaign_name", "adset_name": "adset_name", "ad_name": "ad_name"}.items():
            data[target] = graph_payload.get(source) or graph_payload.get(source.replace("_name", ""))
        data.update({"source_lead_id": str(graph_payload.get("id") or ""), "form_id": graph_payload.get("form_id"), "page_id": graph_payload.get("page_id"), "campaign_id": graph_payload.get("campaign_id"), "ad_id": graph_payload.get("ad_id"), "adset_id": graph_payload.get("adset_id"), "custom_answers": answers})
        meta_debug_log("normalize_lead_end", source_lead_id=data.get("source_lead_id") or context.get("source_lead_id"), mapped_fields=list(data.keys()), **{k: v for k, v in context.items() if k != "source_lead_id"})
        return data
    except Exception:
        meta_debug_log("normalize_lead_exception", traceback=frappe.get_traceback(), **context)
        raise

def _answers(payload):
    answers = {}
    for item in payload.get("field_data") or []:
        key = _norm_key(item.get("name"))
        values = item.get("values") or []
        answers[key] = ", ".join(str(v) for v in values if v is not None)
    return answers

def _mapping(settings=None):
    configured = frappe.conf.get("meta_lead_field_map")
    if not configured and settings:
        configured = getattr(settings, "field_mapping_json", None)
    custom = load_json(configured, {}) if isinstance(configured, str) else configured or {}
    mapping = DEFAULT_FIELD_MAP.copy()
    for target, keys in custom.items():
        mapping[target] = [_norm_key(k) for k in (keys if isinstance(keys, list) else [keys])]
    return mapping

def _first_value(answers, keys):
    values = [answers.get(_norm_key(key)) for key in keys]
    return next((v for v in values if v), None)

def _norm_key(value):
    return str(value or "").strip().lower().replace(" ", "_")
