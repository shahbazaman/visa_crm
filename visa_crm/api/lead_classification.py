import hashlib
import re
import unicodedata

import frappe
from frappe.utils import now_datetime

from visa_crm.api.meta_utils import has_field, load_json, safe_json_dumps


UNCATEGORIZED = "Uncategorized"
CLASSIFICATION_FIELDS = (
    "lead_category",
    "lead_group",
    "responsible_department",
    "classification_source",
    "classification_status",
    "classification_rule",
    "classification_reason",
    "classified_at",
    "classified_by",
)

DESTINATION_KEYWORDS = [
    (r"\bmalaysia\b", "Malaysia"),
    (r"\b(thailand|thai|bangkok|pattaya|phuket)\b", "Thailand"),
    (r"\bbali\b", "Bali"),
    (r"\bandaman\b", "Andaman"),
    (r"\bkashmir\b", "Kashmir"),
    (r"\bcanton\b", "Canton Fair"),
    (r"\b(uk|united kingdom|london|ireland)\b", "UK"),
    (r"\bqatar\b", "Qatar"),
    (r"\b(umrah|hajj|saudi)\b", "Umrah"),
    (r"\b(dubai|uae|abu dhabi)\b", "Dubai"),
    (r"\bvietnam\b", "Vietnam"),
    (r"\b(almaty|kazakhstan)\b", "Almaty"),
    (r"\bmaldives\b", "Maldives"),
    (r"\b(couples|cple)\b", "Couples"),
    (r"\bstamping\b", "Visa Stamping"),
    (r"\b(sales hiring|hiring|recruitment|job)\b", "Sales Hiring"),
    (r"\bticketing\b", "Ticketing"),
    (r"\bsingapore\b", "Singapore"),
    (r"\beurope\b", "Europe"),
    (r"\bschengen\b", "Schengen"),
    (r"\bgeorgia\b", "Georgia"),
    (r"\bbaku\b", "Baku"),
]


def classify_queue(queue_name, claim=None):
    queue = frappe.get_doc("Lead Intake Queue", queue_name)
    if queue.get("classification_source") == "Manual" and queue.get("lead_category"):
        result = _from_existing(queue)
        sync_lead_classification(queue.get("matched_lead"), result, overwrite_automatic=False)
        return _stage_result(result, reused=True)

    payload = load_json(queue.get("normalized_payload"), {})
    _merge_queue_values(payload, queue)
    result = classify_payload(payload, queue.get("lead_source"))

    # Ensure Lead Subcategory exists in database
    ensure_lead_subcategory(result.get("lead_category"), result.get("lead_group"))

    _write_classification("Lead Intake Queue", queue.name, result, overwrite_automatic=True)
    sync_lead_classification(queue.get("matched_lead"), result, overwrite_automatic=False)
    return _stage_result(result, reused=False)


def classify_payload(payload, lead_source=None, rules=None):
    payload = payload or {}
    source = detect_source(payload, lead_source)
    campaign = normalize_text(payload.get("campaign_name"))
    rules = rules if rules is not None else active_rules()

    for rule in rules:
        if _rule_matches(rule, source, campaign):
            category = rule.get("category") or UNCATEGORIZED
            group = derive_group(category, payload)
            return {
                "lead_category": category,
                "lead_group": group,
                "responsible_department": category_department(category),
                "classification_source": "Automatic",
                "classification_status": "Classified",
                "classification_rule": rule.get("name") or rule.get("rule_name"),
                "classification_reason": rule.get("reason") or f"Matched {rule.get('match_field')} rule",
                "classified_at": now_datetime(),
                "classified_by": "Administrator",
                "detected_source": source,
            }

    # Dynamic Fallback Categorization based on keywords in campaign, form name, answers, etc.
    combined_text = normalize_text(" ".join(filter(None, [
        payload.get("campaign_name"),
        payload.get("form_name"),
        payload.get("ad_name"),
        payload.get("adset_name"),
        payload.get("country_interested"),
        payload.get("visa_type"),
        safe_json_dumps(payload.get("custom_answers"))
    ])))

    category = UNCATEGORIZED
    reason = "Dynamic classification from lead content"

    if any(k in combined_text for k in ["hiring", "job", "career", "sales hiring", "interview"]):
        category = "Global Visa" if frappe.db.exists("Lead Category", "Global Visa") else "Reservation"
        reason = "Matched recruitment/hiring keywords"
    elif any(k in combined_text for k in ["package", "malaysia", "thailand", "thai", "bangkok", "pattaya", "bali", "andaman", "kashmir", "dubai", "vietnam", "almaty", "maldives", "couples", "cple", "holiday", "tour", "trip", "canton"]):
        category = "Holidays"
        reason = "Matched holiday destination/tour keywords"
    elif any(k in combined_text for k in ["visa", "stamping", "qatar", "umrah", "uk", "schengen", "tourist visa", "work visa", "embassy", "global visa"]):
        category = "Global Visa"
        reason = "Matched visa keywords"
    elif source == "WhatsApp":
        category = "Reservation"
        reason = "WhatsApp enquiry"
    elif source == "Google Ads":
        category = "Google Ads"
        reason = "Google Ads source"

    group = derive_group(category, payload)
    status = "Classified" if category != UNCATEGORIZED else "Needs Review"

    return {
        "lead_category": category,
        "lead_group": group,
        "responsible_department": category_department(category),
        "classification_source": "Automatic",
        "classification_status": status,
        "classification_rule": None,
        "classification_reason": reason,
        "classified_at": now_datetime(),
        "classified_by": "Administrator",
        "detected_source": source,
    }


def active_rules():
    if not frappe.db.exists("DocType", "Lead Classification Rule"):
        return default_rules()
    rows = frappe.get_all(
        "Lead Classification Rule",
        filters={"enabled": 1},
        fields=["name", "rule_name", "priority", "source_channel", "match_field", "match_type", "match_value", "category", "reason"],
        order_by="priority asc, creation asc",
    )
    return rows


def default_rules():
    return [
        frappe._dict(name="whatsapp-reservation", priority=10, source_channel="WhatsApp", match_field="Source", match_type="Equals", match_value="WhatsApp", category="Reservation", reason="WhatsApp inquiry"),
        frappe._dict(name="email-holidays", priority=50, source_channel="Email", match_field="Source", match_type="Equals", match_value="Email", category="Holidays", reason="Email enquiry — classified as Holidays"),
        frappe._dict(name="meta-global-visa", priority=100, source_channel="Meta", match_field="Campaign Name", match_type="Ends With", match_value="visa", category="Global Visa", reason="Meta campaign ends with visa"),
        frappe._dict(name="meta-holidays", priority=110, source_channel="Meta", match_field="Campaign Name", match_type="Ends With", match_value="package", category="Holidays", reason="Meta campaign ends with package"),
    ]


def detect_source(payload, lead_source=None):
    candidates = [lead_source, payload.get("source_channel"), payload.get("lead_source"), payload.get("source")]
    normalized = " ".join(normalize_text(value) for value in candidates if value)
    if "whatsapp" in normalized:
        return "WhatsApp"
    if "google" in normalized and "ad" in normalized:
        return "Google Ads"
    if lead_source == "Email" or "email" == normalize_text(lead_source or "") or any(
        normalize_text(value or "") == "email" for value in candidates if value
    ):
        return "Email"
    if any((payload.get(key) for key in ("source_lead_id", "facebook_lead_id", "form_id", "facebook_form_id", "campaign_id", "meta_campaign_id"))) or "meta" in normalized or "facebook" in normalized:
        return "Meta"
    return "Manual" if normalized else "Unknown"


def derive_group(category, payload):
    explicit = _first(payload, "custom_destination", "destination", "visa_type", "custom_visa_type", "country_interested")
    if explicit:
        return display_group(explicit)

    # Check text fields for known destinations
    search_text = " ".join(filter(None, [
        str(payload.get("campaign_name") or ""),
        str(payload.get("form_name") or ""),
        str(payload.get("ad_name") or ""),
        str(payload.get("adset_name") or ""),
        safe_json_dumps(payload.get("custom_answers") or {})
    ]))

    for pattern, group_name in DESTINATION_KEYWORDS:
        if re.search(pattern, search_text, re.IGNORECASE):
            return group_name

    campaign = str(payload.get("campaign_name") or "").strip()
    suffix = "package" if category == "Holidays" else "visa" if category == "Global Visa" else None
    if suffix and re.search(rf"\b{suffix}\s*$", normalize_text(campaign)):
        campaign_for_group = re.sub(r"[_\s]+", " ", unicodedata.normalize("NFKC", campaign)).strip()
        stem = re.sub(rf"(?i)\b{suffix}\s*$", "", campaign_for_group).strip(" -_/|.")
        if stem:
            return display_group(stem)
    return "Unspecified"


def display_group(value):
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = re.sub(r"[_\s]+", " ", value).strip(" -_/|.")
    if not value:
        return "Unspecified"
    return " ".join(part.upper() if len(part) <= 3 and part.isalpha() else part.capitalize() for part in value.split())


def normalize_text(value):
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    value = value.replace("_", " ")
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def category_department(category):
    if not category or not frappe.db.exists("DocType", "Lead Category"):
        return None
    return frappe.db.get_value("Lead Category", category, "department")


def ensure_lead_subcategory(category, group):
    """
    Ensures that a Lead Subcategory record exists in the database for the given category and group.
    """
    if not category or not group or group in ("Unspecified", "None", ""):
        return None
    if category == UNCATEGORIZED:
        return None
    if not frappe.db.exists("DocType", "Lead Subcategory"):
        return None
    if not frappe.db.exists("Lead Category", category):
        return None

    existing = frappe.db.exists("Lead Subcategory", {
        "sub_category_name": group,
        "parent_category": category
    }) or frappe.db.get_value("Lead Subcategory", {"sub_category_name": group}, "name")

    if not existing:
        try:
            doc = frappe.get_doc({
                "doctype": "Lead Subcategory",
                "sub_category_name": group,
                "parent_category": category,
                "is_active": 1,
                "sort_order": 10
            })
            doc.insert(ignore_permissions=True)
            return doc.name
        except Exception:
            pass
    return existing


def sync_lead_classification(lead_name, result, overwrite_automatic=False):
    if not lead_name or not frappe.db.exists("CRM Lead", lead_name):
        return
    current = frappe.db.get_value("CRM Lead", lead_name, list(CLASSIFICATION_FIELDS), as_dict=True) or {}
    if current.get("classification_source") == "Manual" and not overwrite_automatic:
        return
    values = {}
    for field in CLASSIFICATION_FIELDS:
        value = result.get(field)
        if has_field("CRM Lead", field) and value is not None and (overwrite_automatic or not current.get(field) or current.get("classification_source") != "Manual"):
            values[field] = value

    # Also ensure Lead Subcategory link if field exists
    if has_field("CRM Lead", "lead_subcategory") and result.get("lead_group"):
        subcat_name = ensure_lead_subcategory(result.get("lead_category"), result.get("lead_group"))
        if subcat_name:
            values["lead_subcategory"] = subcat_name

    if values:
        frappe.db.set_value("CRM Lead", lead_name, values, update_modified=False)


def apply_manual_classification(lead_name, category, group=None, reason=None):
    from visa_crm.api.lead_permissions import accessible_categories, is_management, is_operational

    if not is_operational():
        frappe.throw("Visa CRM operational access required", frappe.PermissionError)

    if not frappe.db.exists("CRM Lead", lead_name):
        frappe.throw("CRM Lead not found", frappe.DoesNotExistError)
    if not frappe.db.exists("Lead Category", {"name": category, "is_active": 1}):
        frappe.throw("Active Lead Category not found", frappe.ValidationError)
    if not is_management() and category not in accessible_categories():
        frappe.throw("Not permitted for this lead category", frappe.PermissionError)
    current = frappe.db.get_value("CRM Lead", lead_name, list(CLASSIFICATION_FIELDS), as_dict=True) or {}
    queue_name = frappe.db.get_value("Lead Intake Queue", {"matched_lead": lead_name}, "name", order_by="creation desc")

    group_name = display_group(group) if group else "Unspecified"
    ensure_lead_subcategory(category, group_name)

    result = {
        "lead_category": category,
        "lead_group": group_name,
        "responsible_department": category_department(category),
        "classification_source": "Manual",
        "classification_status": "Classified",
        "classification_rule": None,
        "classification_reason": reason or "Manually classified by management",
        "classified_at": now_datetime(),
        "classified_by": frappe.session.user,
    }
    _history(lead_name, queue_name, current, result)
    _write_classification("CRM Lead", lead_name, result, overwrite_automatic=True)
    if queue_name:
        _write_classification("Lead Intake Queue", queue_name, result, overwrite_automatic=True)
    return result


def protect_lead_classification(doc, method=None):
    if doc.is_new():
        return
    fields = [field for field in CLASSIFICATION_FIELDS if doc.meta.has_field(field)]
    stored = frappe.db.get_value(doc.doctype, doc.name, fields, as_dict=True) or {}
    changed = [field for field in fields if doc.get(field) != stored.get(field)]
    if changed:
        frappe.throw(
            "Lead classification must be changed with the Lead Management Classify action so its audit history is preserved.",
            frappe.PermissionError,
        )


def _history(lead_name, queue_name, old, new):
    doc = frappe.new_doc("Lead Classification History")
    doc.update({
        "lead": lead_name,
        "queue": queue_name,
        "old_category": old.get("lead_category"),
        "new_category": new.get("lead_category"),
        "old_group": old.get("lead_group"),
        "new_group": new.get("lead_group"),
        "classification_source": new.get("classification_source"),
        "classification_rule": new.get("classification_rule"),
        "reason": new.get("classification_reason"),
        "changed_by": frappe.session.user,
        "changed_at": now_datetime(),
    })
    doc.insert(ignore_permissions=True)


def _write_classification(doctype, name, result, overwrite_automatic=False):
    if not frappe.db.exists(doctype, name):
        return
    fields = [field for field in CLASSIFICATION_FIELDS if has_field(doctype, field)]
    current = frappe.db.get_value(doctype, name, fields, as_dict=True) or {}
    if current.get("classification_source") == "Manual" and not overwrite_automatic:
        return
    values = {field: result.get(field) for field in fields if result.get(field) is not None}
    if values:
        frappe.db.set_value(doctype, name, values, update_modified=False)


def _from_existing(doc):
    return {field: doc.get(field) for field in CLASSIFICATION_FIELDS}


def _stage_result(result, reused):
    digest = hashlib.sha256(safe_json_dumps({key: str(value) for key, value in result.items()}).encode()).hexdigest()
    return {"classification": result, "result_doctype": "Lead Category", "result_name": result.get("lead_category"), "output_hash": digest, "reused": reused}


def _rule_matches(rule, source, campaign):
    required_source = normalize_text(rule.get("source_channel"))
    if required_source and required_source != normalize_text(source):
        return False
    field_value = normalize_text(source if rule.get("match_field") == "Source" else campaign)
    expected = normalize_text(rule.get("match_value"))
    match_type = rule.get("match_type") or "Equals"
    if match_type == "Equals":
        return field_value == expected
    if match_type == "Ends With":
        return field_value.endswith(expected)
    if match_type == "Contains":
        return expected in field_value
    if match_type == "Regex":
        try:
            return bool(re.search(str(rule.get("match_value") or ""), field_value, re.IGNORECASE))
        except re.error:
            return False
    return False


def _merge_queue_values(payload, queue):
    for field in ("source_lead_id", "customer_name", "phone", "email", "country_interested", "visa_type", "campaign_name", "campaign_id", "adset_name", "adset_id", "ad_name", "ad_id", "page_id", "form_id"):
        if not payload.get(field) and queue.get(field):
            payload[field] = queue.get(field)


def _first(payload, *fields):
    for field in fields:
        if payload.get(field):
            return payload.get(field)
    return None


@frappe.whitelist()
def reclassify_all_leads():
    """
    Whitelisted maintenance endpoint to backfill / reclassify any Uncategorized or Unspecified leads.
    """
    updated_count = 0
    subcats_created = 0

    queues = frappe.get_all(
        "Lead Intake Queue",
        filters={"status": ["in", ["Processed", "Lead Created"]]},
        fields=["name", "matched_lead", "normalized_payload", "lead_source", "campaign_name", "custom_answers", "country_interested", "visa_type", "lead_category", "lead_group"]
    )

    for q in queues:
        payload = load_json(q.normalized_payload, {})
        _merge_queue_values(payload, q)
        result = classify_payload(payload, q.lead_source)

        cat = result.get("lead_category")
        grp = result.get("lead_group")

        if cat != UNCATEGORIZED or grp != "Unspecified":
            sub_created = ensure_lead_subcategory(cat, grp)
            if sub_created:
                subcats_created += 1

            _write_classification("Lead Intake Queue", q.name, result, overwrite_automatic=True)
            if q.matched_lead:
                sync_lead_classification(q.matched_lead, result, overwrite_automatic=True)
            updated_count += 1

    frappe.db.commit()
    return {
        "ok": True,
        "total_checked": len(queues),
        "total_updated": updated_count,
        "subcategories_created": subcats_created
    }
