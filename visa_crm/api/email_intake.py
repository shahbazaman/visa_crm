"""
visa_crm/api/email_intake.py
==============================
V1 Email Lead Intake Processor.

Architecture:
    Frappe Communication (incoming email)
        ↓
    email_intake.process_communication(comm_name)
        ↓
    Idempotency check (message_id)
        ↓
    Reply detection (In-Reply-To / References)
        ↓
    Lead Intake Queue created with lead_source=Email
        ↓
    Existing pipeline (NORMALIZE → CLASSIFICATION → CUSTOMER360 → CRM_LEAD → …)

The Email Lead reuses the entire existing resumable pipeline.
No separate pipeline is created.

Email-specific fields on Lead Intake Queue:
  - email_message_id   (idempotency key)
  - email_thread_id    (thread grouping)
  - email_subject      (from email subject)
  - email_in_reply_to  (reply detection)
  - lead_source        (= "Email")
  - raw_email_body     (preserved original body)

Classification:
  - detect_source() returns "Email" for email leads
  - Classification rules match on source_channel="Email"
"""

import hashlib
import re

import frappe
from frappe.utils import now, now_datetime

from visa_crm.api.meta_utils import has_doctype, has_field, log_info, safe_json_dumps, set_values

# ---------------------------------------------------------------------------
# Doc event hook (called from hooks.py)
# ---------------------------------------------------------------------------


def on_communication_insert(doc, method=None):
    """
    Called after a Communication is inserted.
    Enqueues email lead processing if the Communication is an incoming email.
    Uses background queue to avoid blocking the main request.
    """
    if doc.communication_type != "Communication" or doc.sent_or_received != "Received":
        return
    try:
        frappe.enqueue(
            "visa_crm.api.email_intake.process_communication",
            queue="short",
            now=False,
            communication_name=doc.name,
        )
    except Exception:
        # If Redis is unavailable (CLI test mode), process inline
        try:
            process_communication(doc.name)
        except Exception:
            frappe.logger("visa_crm.email").warning(
                f"Failed to process email lead for Communication {doc.name}: {frappe.get_traceback()}"
            )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LEAD_SOURCE_EMAIL = "Email"

# Keywords that suggest a genuine visa / travel enquiry
ENQUIRY_KEYWORDS = re.compile(
    r"\b(visa|passport|travel|tourist|business visa|schengen|uk visa|uae visa|"
    r"us visa|thailand|holiday|package|tour|apply|application|documents|"
    r"processing|immigration|embassy|consulate|enquir|inquiry|booking)\b",
    re.IGNORECASE,
)

PHONE_PATTERN = re.compile(
    r"(?:phone|mobile|cell|tel|contact|whatsapp|call|mob)?[:\s]*"
    r"(\+?[\d\s\-().]{7,20})",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Main entry point — called from Communication hook or scheduler
# ---------------------------------------------------------------------------


def process_communication(communication_name):
    """
    Process a Frappe Communication that may represent an email enquiry.

    Steps:
    1. Load the Communication
    2. Check idempotency (message_id)
    3. Detect if it's a reply to an existing thread → link, skip Lead creation
    4. Check if it's a genuine enquiry
    5. Create Lead Intake Queue with lead_source=Email
    6. Trigger pipeline

    Returns:
        dict with processing result
    """
    if not communication_name or not frappe.db.exists("Communication", communication_name):
        return {"ok": False, "reason": "Communication not found"}

    comm = frappe.get_doc("Communication", communication_name)

    # Only process received emails
    if comm.communication_type != "Communication" or comm.sent_or_received != "Received":
        return {"ok": False, "reason": "Not an incoming email"}

    message_id = (comm.message_id or "").strip()
    in_reply_to = (comm.in_reply_to or "").strip()
    sender_email = _extract_email(comm.sender or "")
    sender_name = _extract_name(comm.sender or "") or sender_email or "Unknown"
    subject = (comm.subject or "").strip()
    body_text = _clean_html(comm.content or "")

    # 1. Idempotency check — don't create duplicate queues for same email
    if message_id and _queue_exists_for_message_id(message_id):
        log_info("email_lead_duplicate_skipped", message_id=message_id, communication=communication_name)
        return {"ok": True, "reason": "Duplicate — already processed", "message_id": message_id}

    # 2. Reply detection — attach to existing Lead instead of creating new one
    if in_reply_to:
        existing_queue = _find_queue_for_thread(in_reply_to)
        if existing_queue:
            _link_reply_to_existing(comm, existing_queue)
            log_info("email_reply_linked", communication=communication_name, queue=existing_queue)
            return {"ok": True, "reason": "Reply linked to existing lead", "queue": existing_queue}

    # 3. Is this a genuine enquiry?
    if not _is_genuine_enquiry(subject, body_text):
        log_info("email_not_an_enquiry", communication=communication_name, subject=subject)
        return {"ok": False, "reason": "Not identified as a customer enquiry"}

    # 4. Extract lead data from email
    lead_data = _extract_lead_data(sender_name, sender_email, subject, body_text, comm)

    # 5. Create Lead Intake Queue
    queue_name = _create_email_queue(comm, lead_data, message_id)

    log_info("email_lead_queue_created", queue=queue_name, communication=communication_name, message_id=message_id)
    return {"ok": True, "queue": queue_name, "message_id": message_id, "lead_data": lead_data}


def process_pending_email_communications(limit=50):
    """
    Scheduler hook: process any received Communications not yet linked to a queue.
    Called every minute alongside the Meta pipeline scheduler.
    """
    if not frappe.db.table_exists("tabCommunication"):
        return 0

    # Find received Communications without a linked Lead Intake Queue
    cutoff_clause = ""
    rows = frappe.db.sql(
        """
        SELECT c.name
        FROM tabCommunication c
        LEFT JOIN `tabLead Intake Queue` q ON q.email_message_id = c.message_id
        WHERE c.communication_type = 'Communication'
          AND c.sent_or_received = 'Received'
          AND c.creation >= DATE_SUB(NOW(), INTERVAL 7 DAY)
          AND q.name IS NULL
        ORDER BY c.creation ASC
        LIMIT %s
        """,
        (limit,),
        as_dict=True,
    )

    processed = 0
    for row in rows:
        try:
            result = process_communication(row.name)
            if result.get("ok"):
                processed += 1
        except Exception:
            frappe.logger("visa_crm.email").warning(
                f"Failed to process Communication {row.name}: {frappe.get_traceback()}"
            )
    if processed:
        frappe.db.commit()
    return processed


# ---------------------------------------------------------------------------
# Helper — Queue existence / idempotency
# ---------------------------------------------------------------------------


def _queue_exists_for_message_id(message_id):
    """Check if a Lead Intake Queue already exists for this message_id."""
    if not has_field("Lead Intake Queue", "email_message_id"):
        # Fall back to checking by a hash in the name
        hashed = _message_id_hash(message_id)
        return frappe.db.exists("Lead Intake Queue", {"name": ["like", f"EMLQ-{hashed}%"]})
    return bool(frappe.db.exists("Lead Intake Queue", {"email_message_id": message_id}))


def _find_queue_for_thread(in_reply_to):
    """Find the Lead Intake Queue that corresponds to the replied-to message."""
    if has_field("Lead Intake Queue", "email_message_id"):
        return frappe.db.get_value("Lead Intake Queue", {"email_message_id": in_reply_to}, "name")
    return None


def _link_reply_to_existing(comm, queue_name):
    """Associate a reply email with the existing queue / CRM Lead."""
    lead = frappe.db.get_value("Lead Intake Queue", queue_name, "matched_lead")
    if lead and frappe.db.exists("CRM Lead", lead):
        # Create a Communication link
        if not frappe.db.exists("Communication", {"reference_doctype": "CRM Lead", "reference_name": lead, "name": comm.name}):
            frappe.db.set_value(
                "Communication", comm.name,
                {"reference_doctype": "CRM Lead", "reference_name": lead},
                update_modified=False,
            )


# ---------------------------------------------------------------------------
# Helper — Queue creation
# ---------------------------------------------------------------------------


def _create_email_queue(comm, lead_data, message_id):
    """Create a Lead Intake Queue for an email lead."""
    hashed = _message_id_hash(message_id or comm.name)
    queue_name = f"EMLQ-{hashed[:8].upper()}"

    # Build normalized payload compatible with the existing pipeline
    normalized = {
        "customer_name": lead_data.get("customer_name"),
        "email": lead_data.get("email"),
        "phone": lead_data.get("phone"),
        "country_interested": lead_data.get("country_interested"),
        "visa_type": lead_data.get("visa_type"),
        "lead_source": LEAD_SOURCE_EMAIL,
        "source_channel": LEAD_SOURCE_EMAIL,
        "campaign_name": None,
        "campaign_id": None,
        "adset_name": None,
        "adset_id": None,
        "ad_name": None,
        "ad_id": None,
        "email_subject": lead_data.get("subject"),
        "email_body": lead_data.get("body"),
    }

    doc = frappe.new_doc("Lead Intake Queue")
    doc.update({
        "lead_source": LEAD_SOURCE_EMAIL,
        "status": "Lead Received",
        "customer_name": lead_data.get("customer_name"),
        "phone": lead_data.get("phone"),
        "email": lead_data.get("email"),
        "country_interested": lead_data.get("country_interested"),
        "normalized_payload": safe_json_dumps(normalized),
    })

    # Set email-specific fields if they exist
    _set_email_fields(doc, comm, lead_data, message_id, normalized)

    try:
        doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
        frappe.db.commit()
    except frappe.DuplicateEntryError:
        pass

    return doc.name


def _set_email_fields(doc, comm, lead_data, message_id, normalized):
    """Set email-specific fields on the Lead Intake Queue doc if they exist."""
    email_field_map = {
        "email_message_id": message_id,
        "email_thread_id": comm.get("in_reply_to") or message_id,
        "email_subject": lead_data.get("subject"),
        "email_in_reply_to": comm.get("in_reply_to"),
        "raw_email_body": lead_data.get("body"),
    }
    meta = doc.meta
    for field, value in email_field_map.items():
        if meta.has_field(field) and value:
            doc.set(field, value)

    # Mark all pipeline stages that are NOT applicable for email leads
    # (WEBHOOK, GRAPH_DOWNLOAD are Meta-only stages — mark as SKIPPED)
    # The pipeline engine will skip them because they are already COMPLETED
    # We mark NORMALIZE as COMPLETED since we already have the normalized payload
    if frappe.db.exists("DocType", "Lead Intake Stage"):
        _pre_mark_email_stages(doc.name)


def _pre_mark_email_stages(queue_name):
    """
    Pre-populate Lead Intake Stage entries for stages that don't apply to email leads.
    WEBHOOK and GRAPH_DOWNLOAD are Meta-only — mark as COMPLETED so pipeline skips them.
    NORMALIZE is also pre-populated since we already extracted the data.
    """
    from frappe.utils import now_datetime

    now_dt = now_datetime()
    for stage_name in ("WEBHOOK", "GRAPH_DOWNLOAD", "NORMALIZE"):
        stage_key = f"{queue_name}:{stage_name}"
        if not frappe.db.exists("Lead Intake Stage", stage_key):
            frappe.db.sql(
                """
                INSERT IGNORE INTO `tabLead Intake Stage`
                (name, queue, stage, state, result_json, creation, modified, modified_by, owner, docstatus)
                VALUES (%s, %s, %s, 'COMPLETED', %s, %s, %s, 'Administrator', 'Administrator', 0)
                """,
                (
                    stage_key, queue_name, stage_name,
                    safe_json_dumps({"reason": "Email lead — stage not applicable", "lead_source": "Email"}),
                    now_dt, now_dt,
                ),
            )


# ---------------------------------------------------------------------------
# Helper — Data extraction
# ---------------------------------------------------------------------------


def _extract_lead_data(sender_name, sender_email, subject, body_text, comm):
    """Extract structured lead fields from email content."""
    phone = _extract_phone(body_text)
    country = _extract_country(subject + " " + body_text)
    visa_type = _extract_visa_type(subject + " " + body_text)

    return {
        "customer_name": sender_name,
        "email": sender_email,
        "phone": phone,
        "country_interested": country,
        "visa_type": visa_type,
        "subject": subject,
        "body": body_text[:5000],  # Truncate for storage
        "communication": comm.name,
    }


def _extract_phone(text):
    """Extract a phone number from email body."""
    matches = PHONE_PATTERN.findall(text)
    for match in matches:
        digits = re.sub(r"[^\d+]", "", match)
        if 7 <= len(digits) <= 15:
            return digits
    return None


def _extract_country(text):
    """Extract country of interest from email text."""
    countries = {
        "Thailand": ["thailand", "thai", "bangkok", "phuket"],
        "UAE": ["uae", "dubai", "abu dhabi", "united arab emirates"],
        "UK": ["uk", "united kingdom", "britain", "england"],
        "Schengen": ["schengen", "europe", "european"],
        "USA": ["usa", "us visa", "united states", "america"],
        "Canada": ["canada", "canadian"],
        "Australia": ["australia", "australian"],
        "India": ["india", "indian"],
    }
    text_lower = text.lower()
    for country, keywords in countries.items():
        if any(kw in text_lower for kw in keywords):
            return country
    return None


def _extract_visa_type(text):
    """Extract visa type from email text."""
    types = {
        "Tourist Visa": ["tourist", "tourism", "vacation", "holiday", "travel"],
        "Business Visa": ["business", "work permit", "employment"],
        "Student Visa": ["student", "study", "education"],
        "Family Visa": ["family", "spouse", "dependent"],
        "Transit Visa": ["transit", "stopover"],
    }
    text_lower = text.lower()
    for visa_type, keywords in types.items():
        if any(kw in text_lower for kw in keywords):
            return visa_type
    return None


def _is_genuine_enquiry(subject, body_text):
    """Determine if this email is a genuine customer visa/travel enquiry."""
    combined = (subject + " " + body_text).lower()
    return bool(ENQUIRY_KEYWORDS.search(combined))


def _extract_email(sender_string):
    """Extract email address from sender string like 'Name <email@example.com>'."""
    match = re.search(r"<([^>]+)>", sender_string)
    if match:
        return match.group(1).strip()
    # Check if the sender string itself is an email
    if "@" in sender_string:
        return sender_string.strip()
    return ""


def _extract_name(sender_string):
    """Extract display name from sender string like 'Name <email@example.com>'."""
    match = re.search(r"^(.+?)\s*<", sender_string)
    if match:
        name = match.group(1).strip().strip('"').strip("'")
        if name:
            return name
    return ""


def _clean_html(html_content):
    """Strip HTML tags to get plain text."""
    text = re.sub(r"<[^>]+>", " ", html_content or "")
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _message_id_hash(message_id):
    """Generate a deterministic short hash from a message_id."""
    return hashlib.sha256((message_id or "").encode()).hexdigest()
