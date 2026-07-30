from fnmatch import fnmatchcase
import re
import frappe
from visa_crm.api.meta_utils import load_json, meta_debug_log, normalize_phone, safe_json_dumps

MAPPING_VERSION="1"
DEFAULT_FIELD_MAP = {
    "customer_name": ["full_name", "name", "first_name", "last_name"],
    "phone": ["phone_number", "phone", "mobile", "mobile_number"],
    "email": ["email", "email_address"],
    "country_interested": ["country", "country_interested", "destination_country", "preferred_country"],
    "visa_type": ["visa_type", "visa_category", "type_of_visa"],
    "whatsapp": ["whatsapp", "whatsapp_number", "wa_number"]
}
DEFAULT_FIELD_ALIASES = {
    "customer_name": ["full_name", "name", "*full*name*"],
    "first_name": ["first_name", "given_name"],
    "last_name": ["last_name", "surname", "family_name"],
    "phone": ["phone", "phone_number", "mobile", "mobile_number", "*phone*number*", "*mobile*number*"],
    "email": ["email", "email_address", "*email*address*"],
    "city": ["city", "current_city", "*city*"],
    "country_interested": ["country", "country_interested", "destination_country", "preferred_country", "*country*interested*", "*destination*country*"],
    "budget": ["budget", "*budget*", "നിങ്ങളുടെ*budget*എത്രയാണ്?"],
    "travel_date": ["travel_date", "preferred_travel_date", "*travel*date*"],
    "passport": ["passport", "do_you_have_a_valid_passport?", "*valid*passport*", "*passport*"],
    "visa_type": ["visa_type", "visa_category", "type_of_visa", "*visa*type*", "*visa*category*"],
    "destination": ["destination", "travel_destination", "*destination*"],
    "travel_month": ["travel_month", "*travel*month*", "*trip*month*", "ബാലി*trip*ഏത്*മാസം*പ്ലാൻ_ചെയ്യുന്നു?"],
    "message": ["message", "customer_message", "enquiry", "inquiry"],
    "notes": ["notes", "additional_notes", "comments"],
    "whatsapp": ["whatsapp", "whatsapp_number", "wa_number", "*whatsapp*number*"]
}

def normalize_lead(graph_payload, settings=None, context=None):
    context = context or {}
    meta_debug_log("normalize_lead_start", **context)
    try:
        answers = _answers(graph_payload)
        mapping = _aliases(settings)
        data = {field: _first_value(answers, keys) for field, keys in mapping.items()}
        if not data.get("customer_name"):
            data["customer_name"] = " ".join(filter(None, [answers.get("first_name"), answers.get("last_name")])) or None
        data.update(_derived_fields(data))
        data["phone"] = normalize_phone(data.get("phone"))
        data["whatsapp"] = normalize_phone(data.get("whatsapp"))
        data["email"] = (data.get("email") or "").strip().lower() or None
        for target, source in {"campaign_name": "campaign_name", "adset_name": "adset_name", "ad_name": "ad_name"}.items():
            data[target] = graph_payload.get(source) or graph_payload.get(source.replace("_name", ""))
        data.update({"source_lead_id": str(graph_payload.get("id") or ""), "form_id": graph_payload.get("form_id"), "page_id": graph_payload.get("page_id"), "campaign_id": graph_payload.get("campaign_id"), "ad_id": graph_payload.get("ad_id"), "adset_id": graph_payload.get("adset_id"), "custom_answers": answers, "meta_fields": answers, "meta_raw_fields": safe_json_dumps(answers)})
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
        answers[key] = str(values[0]).strip() if values and values[0] is not None else None
    return answers

def _derived_fields(mapped):
    data = dict(mapped)
    data["phone"] = data.get("phone") or data.get("phone_number")
    data["country_interested"] = data.get("country_interested") or data.get("country") or data.get("destination")
    data["custom_budget"] = data.get("custom_budget") or data.get("budget")
    data["custom_travel_month"] = data.get("custom_travel_month") or data.get("travel_month")
    data["custom_destination"] = data.get("custom_destination") or data.get("destination")
    data["custom_passport_status"] = data.get("custom_passport_status") or data.get("passport")
    data["custom_visa_type"] = data.get("custom_visa_type") or data.get("visa_type")
    data["notes"] = data.get("notes") or data.get("message")
    return {key: value for key, value in data.items() if value}

def _aliases(settings=None):
    mapping = {target: list(keys) for target, keys in DEFAULT_FIELD_ALIASES.items()}
    configured = frappe.conf.get("meta_lead_field_map")
    if not configured and settings:
        configured = getattr(settings, "field_mapping_json", None)
    custom = load_json(configured, {}) if isinstance(configured, str) else configured or {}
    for target, keys in custom.items():
        mapping[target] = [_norm_key(k) for k in (keys if isinstance(keys, list) else [keys])]
    configured_aliases = frappe.conf.get("meta_lead_field_aliases")
    if not configured_aliases and settings:
        configured_aliases = getattr(settings, "field_aliases_json", None) or getattr(settings, "field_alias_mapping_json", None)
    custom_aliases = load_json(configured_aliases, {}) if isinstance(configured_aliases, str) else configured_aliases or {}
    for target, keys in custom_aliases.items():
        mapping.setdefault(target, [])
        mapping[target].extend(keys if isinstance(keys, list) else [keys])
    for target, keys in DEFAULT_FIELD_MAP.items():
        mapping.setdefault(target, []).extend(keys)
    return {target: list(dict.fromkeys(_norm_pattern(key) for key in keys if key)) for target, keys in mapping.items()}

def _mapping(settings=None):
    mapping = _aliases(settings)
    return mapping

def _first_value(answers, keys):
    for pattern in keys:
        if "*" not in pattern and answers.get(pattern):
            return answers[pattern]
        for key, value in answers.items():
            if value and fnmatchcase(key, pattern):
                return value
    return None

def _norm_key(value):
    return re.sub(r"_+", "_", re.sub(r"[^\w]+", "_", str(value or "").strip().lower())).strip("_")

def _norm_pattern(value):
    return re.sub(r"_+", "_", re.sub(r"[^\w*]+", "_", str(value or "").strip().lower())).strip("_")
