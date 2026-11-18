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

# Suffix pattern matching Meta campaign conventions (visa, package, campaign, campign, leads)
META_CAMPAIGN_SUFFIX_PATTERN = re.compile(r"(?i)(?:^|[\s_\-]+)(visa|package|campaign|campign|leads)\s*$")

# Generic non-destination words that should not become subcategories
GENERIC_WORDS = {
    "special", "holiday", "holidays", "travel", "summer", "winter", "best", "top", "new",
    "offer", "offers", "deal", "deals", "ad", "poster", "leads", "lead", "campaign",
    "campign", "v1", "test", "promo", "awareness", "general", "inquiry", "direct"
}

# Comprehensive destination configuration: (Canonical Name, [Regex Patterns])
# Ordered with multi-word phrases and specific entities before single-word substrings
DESTINATION_CONFIG = [
    # Multi-word & phrase destinations
    ("United Arab Emirates", [r"\b(united\s*arab\s*emirates|uae)\b"]),
    ("Abu Dhabi", [r"\babu\s*dhabi\b"]),
    ("Dubai", [r"\bdubai\b"]),
    ("Saudi Arabia", [r"\bsaudi(\s*arabia)?\b"]),
    ("Umrah", [r"\b(umrah|hajj)\b"]),
    ("South Africa", [r"\bsouth\s*africa\b"]),
    ("South Korea", [r"\bsouth\s*korea\b", r"\bkorea\b"]),
    ("Hong Kong", [r"\bhong\s*kong\b"]),
    ("Sri Lanka", [r"\bsri\s*lanka\b"]),
    ("New Zealand", [r"\bnew\s*zealand\b"]),
    ("United Kingdom", [r"\b(united\s*kingdom|london|britain)\b"]),
    ("UK", [r"\buk\b"]),
    ("United States", [r"\b(united\s*states|america)\b"]),
    ("USA", [r"\busa\b"]),
    ("Ho Chi Minh", [r"\b(ho\s*chi\s*minh|saigon|hcm)\b"]),
    ("Da Nang", [r"\b(da\s*nang|danang)\b"]),
    ("Hanoi", [r"\bhanoi\b"]),
    ("Canton Fair", [r"\bcanton(\s*fair)?\b"]),
    ("Sales Hiring", [r"\b(sales\s*hiring|hiring|hirng|recruitment|recruiter|job|career|interview)\b"]),
    ("Visa Stamping", [r"\b(visa\s*stamping|stamping)\b"]),
    ("Ticketing", [r"\bticketing\b"]),
    ("Couples", [r"\b(couples|cple)\b"]),

    # Single-word destinations
    ("Azerbaijan", [r"\bazerbaijan\b", r"\bazerbijan\b", r"\bazerbaizan\b"]),
    ("Baku", [r"\bbaku\b"]),
    ("Vietnam", [r"\bvietnam\b", r"\bveitnam\b", r"\bviet\s*nam\b"]),
    ("Thailand", [r"\b(thailand|thai|bangkok|pattaya|phuket)\b"]),
    ("Malaysia", [r"\bmalaysia\b"]),
    ("Singapore", [r"\bsingapore\b"]),
    ("Bali", [r"\bbali\b", r"\bindonesia\b"]),
    ("Maldives", [r"\bmaldives\b"]),
    ("Andaman", [r"\bandaman\b"]),
    ("Kashmir", [r"\b(kashmir|kshmir)\b"]),
    ("Almaty", [r"\balmaty\b"]),
    ("Kazakhstan", [r"\bkazakhstan\b"]),
    ("Uzbekistan", [r"\buzbekistan\b"]),
    ("Georgia", [r"\bgeorgia\b"]),
    ("Armenia", [r"\barmenia\b"]),
    ("Turkey", [r"\b(turkey|turkiye)\b"]),
    ("Europe", [r"\beurope\b"]),
    ("Schengen", [r"\bschengen\b"]),
    ("Qatar", [r"\bqatar\b"]),
    ("Oman", [r"\boman\b"]),
    ("Nepal", [r"\bnepal\b"]),
    ("Bhutan", [r"\bbhutan\b"]),
    ("Japan", [r"\bjapan\b"]),
    ("Mauritius", [r"\bmauritius\b"]),
    ("Seychelles", [r"\bseychelles\b"]),
    ("Egypt", [r"\begypt\b"]),
    ("Kenya", [r"\bkenya\b"]),
    ("Tanzania", [r"\btanzania\b"]),
    ("Russia", [r"\brussia\b"]),
    ("Canada", [r"\bcanada\b"]),
    ("Australia", [r"\baustralia\b"]),
    ("Germany", [r"\bgermany\b"]),
    ("France", [r"\bfrance\b"]),
    ("Italy", [r"\bitaly\b"]),
    ("Spain", [r"\bspain\b"]),
    ("Portugal", [r"\bportugal\b"]),
    ("Netherlands", [r"\b(netherlands|holland)\b"]),
    ("Belgium", [r"\bbelgium\b"]),
    ("Switzerland", [r"\bswitzerland\b"]),
    ("Austria", [r"\baustria\b"]),
    ("Greece", [r"\bgreece\b"]),
    ("Poland", [r"\bpoland\b"]),
    ("Sweden", [r"\bsweden\b"]),
    ("Norway", [r"\bnorway\b"]),
    ("Denmark", [r"\bdenmark\b"]),
    ("Finland", [r"\bfinland\b"]),
    ("Ireland", [r"\bireland\b"]),
]

# Legacy tuple maintained for backward compatibility with external references
DESTINATION_KEYWORDS = [(pats[0], canonical) for canonical, pats in DESTINATION_CONFIG]


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

    # 1. Evaluate explicit rules in deterministic priority order
    for rule in rules:
        if _rule_matches(rule, source, campaign):
            category = rule.get("category") or UNCATEGORIZED
            group = derive_group(category, payload)
            ensure_lead_subcategory(category, group)
            rule_name = rule.get("name") or rule.get("rule_name")
            reason = rule.get("reason") or f"Matched {rule.get('match_field')} rule"
            if payload.get("campaign_name"):
                reason = f"{reason} (Campaign: '{payload.get('campaign_name')}', Destination: '{group}')"
            return {
                "lead_category": category,
                "lead_group": group,
                "responsible_department": category_department(category),
                "classification_source": "Automatic",
                "classification_status": "Classified",
                "classification_rule": rule_name,
                "classification_reason": reason,
                "classified_at": now_datetime(),
                "classified_by": "Administrator",
                "detected_source": source,
            }

    # 2. Dynamic Fallback Categorization based on keywords in campaign, form name, answers, etc.
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

    if any(k in combined_text for k in ["hiring", "hirng", "job", "career", "sales hiring", "interview"]):
        category = "Global Visa" if frappe.db.exists("Lead Category", "Global Visa") else "Reservation"
        reason = "Matched recruitment/hiring keywords"
    elif any(k in combined_text for k in [
        "package", "malaysia", "thailand", "thai", "bangkok", "pattaya", "bali", "andaman", "kashmir", "kshmir",
        "dubai", "vietnam", "veitnam", "almaty", "maldives", "couples", "cple", "holiday", "tour", "trip", "canton",
        "azerbaijan", "baku", "hanoi", "da nang", "georgia", "armenia", "turkey", "sri lanka", "nepal", "bhutan",
        "japan", "korea", "hong kong", "mauritius", "seychelles", "egypt", "kenya", "tanzania", "south africa", "russia"
    ]):
        category = "Holidays"
        reason = "Matched holiday destination/tour keywords"
    elif any(k in combined_text for k in ["visa", "stamping", "qatar", "umrah", "uk", "schengen", "tourist visa", "work visa", "embassy", "global visa", "usa"]):
        category = "Global Visa"
        reason = "Matched visa keywords"
    elif source == "WhatsApp":
        category = "Reservation"
        reason = "WhatsApp enquiry"
    elif source == "Google Ads":
        if frappe.db.exists("Lead Category", "Google Ads") and any(r.get("category") == "Google Ads" for r in rules):
            category = "Google Ads"
            reason = "Google Ads source"

    group = derive_group(category, payload)
    if category != UNCATEGORIZED:
        ensure_lead_subcategory(category, group)
        status = "Classified"
        reason = f"{reason} | Destination: '{group}'"
    else:
        status = "Needs Review"
        reason = "No classification rule matched"

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
    # Ensure all mandatory default rules are incorporated
    db_keys = {(r.get("source_channel"), r.get("match_field"), r.get("match_value")) for r in rows}
    merged = list(rows)
    for def_rule in default_rules():
        key = (def_rule.get("source_channel"), def_rule.get("match_field"), def_rule.get("match_value"))
        if key not in db_keys:
            merged.append(def_rule)
    merged.sort(key=lambda x: (x.get("priority", 100), str(x.get("name"))))
    return merged


def default_rules():
    return [
        frappe._dict(name="whatsapp-reservation", rule_name="WhatsApp to Reservation", priority=10, source_channel="WhatsApp", match_field="Source", match_type="Equals", match_value="WhatsApp", category="Reservation", reason="WhatsApp inquiry"),
        frappe._dict(name="email-holidays", rule_name="Email to Holidays", priority=50, source_channel="Email", match_field="Source", match_type="Equals", match_value="Email", category="Holidays", reason="Email enquiry — classified as Holidays"),
        frappe._dict(name="meta-global-visa", rule_name="Meta Visa Campaign", priority=100, source_channel="Meta", match_field="Campaign Name", match_type="Ends With", match_value="visa", category="Global Visa", reason="Meta campaign ends with visa"),
        frappe._dict(name="meta-holidays", rule_name="Meta Package Campaign", priority=110, source_channel="Meta", match_field="Campaign Name", match_type="Ends With", match_value="package", category="Holidays", reason="Meta campaign ends with package"),
        frappe._dict(name="meta-holiday-campaign", rule_name="Meta Holiday Campaign Suffix", priority=120, source_channel="Meta", match_field="Campaign Name", match_type="Ends With", match_value="campaign", category="Holidays", reason="Meta campaign ends with campaign"),
        frappe._dict(name="meta-holiday-campign", rule_name="Meta Holiday Campign Suffix", priority=121, source_channel="Meta", match_field="Campaign Name", match_type="Ends With", match_value="campign", category="Holidays", reason="Meta campaign ends with campign"),
        frappe._dict(name="meta-holiday-leads", rule_name="Meta Holiday Leads Suffix", priority=122, source_channel="Meta", match_field="Campaign Name", match_type="Ends With", match_value="leads", category="Holidays", reason="Meta campaign ends with leads"),
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


def extract_destination(payload, category=None):
    """
    Extracts the destination or subject from lead metadata in documented precedence:
    1. Explicit destination fields (custom_destination, destination, country_interested).
    2. Suffix-stripped Campaign Name stem matched against destination terms.
    3. Campaign Name / Ad Name / Form Name / Answers keyword search against DESTINATION_CONFIG.
    4. Clean Campaign Name stem fallback.
    5. Fallback: 'Unspecified'.
    """
    payload = payload or {}

    # 1. Explicit fields
    explicit = _first(payload, "custom_destination", "destination", "country_interested")
    if not explicit and category != "Holidays":
        explicit = _first(payload, "visa_type", "custom_visa_type")
    if explicit:
        str_exp = str(explicit).strip()
        if "<test" in str_exp.lower() or "dummy data" in str_exp.lower() or str_exp.lower().startswith("test lead"):
            explicit = None
        else:
            for canonical, patterns in DESTINATION_CONFIG:
                for pat in patterns:
                    if re.search(pat, str_exp, re.IGNORECASE):
                        return canonical
            return display_group(explicit)

    # 2. Suffix-stripped Campaign Name stem matching
    raw_campaign = str(payload.get("campaign_name") or "").strip()
    if raw_campaign:
        stem = META_CAMPAIGN_SUFFIX_PATTERN.sub("", raw_campaign).strip(" -_/|.")
        if stem:
            for canonical, patterns in DESTINATION_CONFIG:
                for pat in patterns:
                    if re.search(pat, stem, re.IGNORECASE):
                        return canonical

    # 3. Search combined text across all available metadata
    search_text = " ".join(filter(None, [
        raw_campaign,
        str(payload.get("form_name") or ""),
        str(payload.get("ad_name") or ""),
        str(payload.get("adset_name") or ""),
        safe_json_dumps(payload.get("custom_answers") or {})
    ]))

    for canonical, patterns in DESTINATION_CONFIG:
        for pat in patterns:
            if re.search(pat, search_text, re.IGNORECASE):
                return canonical

    # 4. Clean stem fallback if campaign has a valid destination word
    if raw_campaign:
        stem = META_CAMPAIGN_SUFFIX_PATTERN.sub("", raw_campaign).strip(" -_/|.")
        cleaned_stem = normalize_text(stem)
        words = cleaned_stem.split()
        if words and not all(w in GENERIC_WORDS for w in words) and len(cleaned_stem) > 2:
            # Strip trailing/leading generic words (e.g. 'Europe Holiday' -> 'Europe')
            filtered_words = [w for w in words if w not in GENERIC_WORDS]
            if filtered_words:
                cleaned_filtered = " ".join(filtered_words)
                for canonical, patterns in DESTINATION_CONFIG:
                    for pat in patterns:
                        if re.search(pat, cleaned_filtered, re.IGNORECASE):
                            return canonical
                return display_group(cleaned_filtered)
            return display_group(stem)

    return "Unspecified"


def derive_group(category, payload):
    """
    Derives the subcategory / lead_group name, ensuring case-normalization
    and reusing existing subcategories under the given parent category if available.
    """
    if not category or category == UNCATEGORIZED:
        return "Unspecified"

    dest = extract_destination(payload, category=category)
    if dest and dest != "Unspecified" and category and category != UNCATEGORIZED:
        try:
            norm_dest = normalize_text(dest)
            for sub in frappe.get_all("Lead Subcategory", filters={"parent_category": category}, fields=["sub_category_name"]):
                if normalize_text(sub.sub_category_name) == norm_dest:
                    return sub.sub_category_name
        except Exception:
            pass
    return dest or "Unspecified"


def display_group(value):
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = re.sub(r"[_\s]+", " ", value).strip(" -_/|.")
    if not value:
        return "Unspecified"
    UPPERCASE_WORDS = {"USA", "UK", "UAE"}
    words = []
    for part in value.split():
        if part.upper() in UPPERCASE_WORDS:
            words.append(part.upper())
        elif len(part) <= 3 and part.isalpha() and part.isupper():
            words.append(part.upper())
        else:
            words.append(part.capitalize())
    return " ".join(words)


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
    Returns the Lead Subcategory name (ID) or None.
    Reuses existing records case-insensitively and space-normalized.
    Strictly isolates by parent_category.
    """
    if not category or not group or group in ("Unspecified", "None", ""):
        return None
    if category == UNCATEGORIZED:
        return None
    if not frappe.db.exists("DocType", "Lead Subcategory"):
        return None
    if not frappe.db.exists("Lead Category", category):
        return None

    clean_group = display_group(group)
    norm_group = normalize_text(clean_group)

    # 1. Look for existing subcategory under this exact parent category
    existing_subcats = frappe.get_all(
        "Lead Subcategory",
        filters={"parent_category": category},
        fields=["name", "sub_category_name", "is_active"]
    )
    for sub in existing_subcats:
        if normalize_text(sub.sub_category_name) == norm_group:
            return sub.name

    # 2. Not found under this parent category -> Create it
    try:
        doc = frappe.get_doc({
            "doctype": "Lead Subcategory",
            "sub_category_name": clean_group,
            "parent_category": category,
            "is_active": 1,
            "sort_order": 10
        })
        doc.insert(ignore_permissions=True)
        return doc.name
    except Exception as exc:
        for sub in frappe.get_all("Lead Subcategory", filters={"parent_category": category}, fields=["name", "sub_category_name"]):
            if normalize_text(sub.sub_category_name) == norm_group:
                return sub.name
        frappe.logger("visa_crm.classification").warning(f"Failed to create Lead Subcategory '{clean_group}' for '{category}': {exc}")
        return None


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
    match_field = rule.get("match_field")
    field_value = normalize_text(source if match_field == "Source" else campaign)
    expected = normalize_text(rule.get("match_value"))
    match_type = rule.get("match_type") or "Equals"

    if match_type == "Equals":
        return field_value == expected

    if match_type == "Ends With":
        if field_value == expected:
            return True
        return bool(re.search(rf"(?:^|[\s_\-]+){re.escape(expected)}$", field_value))

    if match_type == "Contains":
        return bool(re.search(rf"\b{re.escape(expected)}\b", field_value))

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
def backfill_meta_leads_classification(dry_run=True, force=False):
    """
    Backfill and reclassify affected Meta leads.
    Safely identifies leads in Uncategorized or with missing/incomplete classification.
    When dry_run=True, returns report of proposed changes without mutating data.
    When dry_run=False, applies the updates and commits.
    """
    dry_run = frappe.parse_json(dry_run) if isinstance(dry_run, str) else bool(dry_run)
    force = frappe.parse_json(force) if isinstance(force, str) else bool(force)

    queues = frappe.get_all(
        "Lead Intake Queue",
        filters={"status": ["not in", ["Ignored Test Event"]]},
        fields=[
            "name", "matched_lead", "normalized_payload", "lead_source",
            "campaign_name", "custom_answers", "country_interested", "visa_type",
            "lead_category", "lead_group", "classification_source", "classification_reason"
        ],
        order_by="creation asc",
        limit_page_length=5000
    )

    eligible_changes = []
    unmatched_records = []
    reused_subcats = set()
    created_subcats = set()

    for q in queues:
        if q.get("classification_source") == "Manual" and not force:
            continue

        current_cat = q.get("lead_category") or UNCATEGORIZED
        current_grp = q.get("lead_group") or "Unspecified"

        payload = load_json(q.normalized_payload, {})
        _merge_queue_values(payload, q)
        result = classify_payload(payload, q.lead_source)

        new_cat = result.get("lead_category")
        new_grp = result.get("lead_group")

        is_affected = (
            (current_cat in (UNCATEGORIZED, None, "") and new_cat != UNCATEGORIZED)
            or (current_grp in ("Unspecified", None, "") and new_grp != "Unspecified")
        )

        if not is_affected:
            if current_cat in (UNCATEGORIZED, None, "") and new_cat == UNCATEGORIZED:
                unmatched_records.append({
                    "queue": q.name,
                    "lead": q.get("matched_lead"),
                    "campaign_name": q.get("campaign_name"),
                    "source": q.get("lead_source"),
                    "reason": result.get("classification_reason")
                })
            continue

        subcat_action = "none"
        if new_cat and new_cat != UNCATEGORIZED and new_grp and new_grp != "Unspecified":
            norm_grp = normalize_text(new_grp)
            existing_sub = None
            if frappe.db.exists("DocType", "Lead Subcategory"):
                for s in frappe.get_all("Lead Subcategory", filters={"parent_category": new_cat}, fields=["name", "sub_category_name"]):
                    if normalize_text(s.sub_category_name) == norm_grp:
                        existing_sub = s.sub_category_name
                        break
            if existing_sub:
                subcat_action = f"reuse ('{existing_sub}')"
                reused_subcats.add(f"{new_cat} -> {existing_sub}")
            else:
                subcat_action = f"create ('{new_grp}')"
                created_subcats.add(f"{new_cat} -> {new_grp}")

        change_entry = {
            "queue": q.name,
            "lead": q.get("matched_lead"),
            "campaign_name": q.get("campaign_name"),
            "current_category": current_cat,
            "proposed_category": new_cat,
            "current_group": current_grp,
            "proposed_group": new_grp,
            "subcategory_action": subcat_action,
            "rule": result.get("classification_rule"),
            "reason": result.get("classification_reason")
        }
        eligible_changes.append(change_entry)

        if not dry_run:
            ensure_lead_subcategory(new_cat, new_grp)
            _write_classification("Lead Intake Queue", q.name, result, overwrite_automatic=True)
            if q.matched_lead and frappe.db.exists("CRM Lead", q.matched_lead):
                sync_lead_classification(q.matched_lead, result, overwrite_automatic=True)

    if not dry_run:
        frappe.db.commit()

    return {
        "ok": True,
        "dry_run": dry_run,
        "total_checked": len(queues),
        "eligible_updates": len(eligible_changes),
        "subcategories_to_create": sorted(list(created_subcats)),
        "subcategories_reused": sorted(list(reused_subcats)),
        "unmatched_count": len(unmatched_records),
        "changes_sample": eligible_changes[:20],
        "all_changes": eligible_changes if dry_run else [],
        "unmatched_sample": unmatched_records[:10]
    }


@frappe.whitelist()
def reclassify_all_leads():
    """
    Whitelisted legacy endpoint. Calls backfill_meta_leads_classification(dry_run=False).
    """
    res = backfill_meta_leads_classification(dry_run=False)
    return {
        "ok": True,
        "total_checked": res["total_checked"],
        "total_updated": res["eligible_updates"],
        "subcategories_created": len(res["subcategories_to_create"])
    }
