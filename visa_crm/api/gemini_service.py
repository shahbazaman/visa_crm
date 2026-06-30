import os
import time
import json
import requests

import frappe
from frappe.utils import cint, now, add_days, today
from frappe.utils.file_manager import get_file_path

# Supported audio extensions
AUDIO_EXTENSIONS = (".m4a", ".mp3", ".wav", ".aac", ".mpeg", ".ogg", ".webm", ".mp4")

# Max lengths to avoid Data-too-long DB errors for Data fields
_MAX_DATA = 255


def _trunc(value, length=_MAX_DATA):
    if not value:
        return value
    if not isinstance(value, str):
        value = str(value)
    return value[:length]
def rating(v):
    if not v:
        return 0
    v=str(v)
    if "/" in v:
        return float(
            v.split("/")[0]
        )
    v=v.replace("%","")
    try:
        return float(v)
    except:
        return 0
def score(v):
    if not v:
        return 0
    v=str(v)
    if "/" in v:
        v=v.split("/")[0]
    try:
        return float(v)
    except:
        return 0
def percent(v):
    if not v:
        return 0
    v=str(v).replace("%","")
    try:
        return float(v)
    except:
        return 0

def _clean_text(value):
    if value is None:
        return None
    text = str(value).strip()
    while text.endswith("|"):
        text = text[:-1].strip()
    return _trunc(text)

def append_ai_error(doc, message):
    if not message:
        return
    message = _trunc(str(message), 1000)
    if getattr(doc, "ai_error", None):
        doc.ai_error = f"{doc.ai_error}\n{message}"
    else:
        doc.ai_error = message


def set_call_status(docname, status, error_message=None, overwrite=False, only_if_current_status=None):
    current_error = frappe.db.get_value("Call Intelligence", docname, "ai_error")
    if error_message:
        error_message = _trunc(str(error_message), 1000)
        if overwrite or not current_error:
            combined_error = error_message
        else:
            combined_error = f"{current_error}\n{error_message}"
    else:
        combined_error = current_error or ""

    if only_if_current_status is not None:
        if only_if_current_status == "":
            sql = "UPDATE `tabCall Intelligence` SET processing_status=%s, ai_error=%s WHERE name=%s AND (processing_status=%s OR processing_status IS NULL OR processing_status='')"
            params = (status, combined_error, docname, only_if_current_status)
        else:
            sql = "UPDATE `tabCall Intelligence` SET processing_status=%s, ai_error=%s WHERE name=%s AND processing_status=%s"
            params = (status, combined_error, docname, only_if_current_status)
    else:
        sql = "UPDATE `tabCall Intelligence` SET processing_status=%s, ai_error=%s WHERE name=%s"
        params = (status, combined_error, docname)

    frappe.db.sql(sql, params)
    frappe.db.commit()
    if only_if_current_status is not None:
        cursor = getattr(frappe.db, '_cursor', None)
        return bool(cursor and cursor.rowcount)
    return True

def get_api_key():
    settings = frappe.get_single("Gemini Settings")
    return settings.get_password("gemini_api_key")
def _gemini_headers(extra=None):
    headers = {"x-goog-api-key": get_api_key()}
    if extra:
        headers.update(extra)
    return headers


def _gemini_error_message(response):
    body = ""
    try:
        body = response.text or ""
    except Exception:
        body = ""
    body = body[:1000]
    if body:
        return f"Gemini API returned HTTP {response.status_code} {response.reason}: {body}"
    return f"Gemini API returned HTTP {response.status_code} {response.reason}"


def _gemini_request(method, url, *, retries=3, timeout=180, **kwargs):
    retry_statuses = {429, 500, 502, 503, 504}
    last_response = None

    for attempt in range(retries + 1):
        response = requests.request(method, url, timeout=timeout, **kwargs)
        last_response = response

        if response.status_code not in retry_statuses:
            break

        if attempt < retries:
            time.sleep(min(2 ** attempt, 8))

    if last_response is None:
        raise RuntimeError("Gemini request did not return a response")

    if last_response.status_code >= 400:
        raise requests.HTTPError(_gemini_error_message(last_response), response=last_response)

    return last_response

def upload_audio_to_gemini(file_path):
    """Upload raw audio bytes to Gemini Files API and return file_uri."""
    upload_url = "https://generativelanguage.googleapis.com/upload/v1beta/files"

    filename = os.path.basename(file_path)
    ext = os.path.splitext(filename)[1].lower()
    mime_map = {
        ".mp3": "audio/mpeg",
        ".mpeg": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".mp4": "audio/mp4",
        ".wav": "audio/wav",
        ".aac": "audio/aac",
        ".ogg": "audio/ogg",
        ".webm": "audio/webm",
    }
    content_type = mime_map.get(ext, "audio/mpeg")

    headers = {
        "X-Goog-Upload-Protocol": "raw",
        "X-Goog-Upload-File-Name": filename,
        "Content-Type": content_type,
    }

    with open(file_path, "rb") as fh:
        r = _gemini_request("POST", upload_url, headers=_gemini_headers(headers), data=fh)
    return r.json()["file"]["uri"]


def wait_until_active(file_uri, timeout_sec=60):
    file_name = file_uri.split("/")[-1]
    url = f"https://generativelanguage.googleapis.com/v1beta/files/{file_name}"

    start = time.time()
    while time.time() - start < timeout_sec:
        r = _gemini_request("GET", url, headers=_gemini_headers(), retries=2, timeout=60)
        try:
            data = r.json()
        except Exception:
            time.sleep(2)
            continue
        if data.get("state") == "ACTIVE":
            return True
        time.sleep(2)
    return False


def analyze_audio(file_uri):
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

    prompt = """
You are an assistant that analyzes audio conversations. Reply using ONLY labeled fields in this exact format.
Each field must be on the same line as its label, and fields must be separated by a pipe character (`|`).
If a field is unknown, write `None`.
Do not add any extra explanation or commentary.

Summary: <short summary of the call>
Emotion: <overall sentiment>
Lead Intent: <customer intent>
Customer Name: <customer name>
Customer Phone Number: <customer phone>
Customer Email: <customer email>
Employee Phone: <employee phone>
Country of Interest: <country of interest>
Visa Type: <visa type>
Recommended Visa: <recommended visa>
Alternate Visa: <alternate visa>
Recommendation Reason: <reason>
Lead Score: <numeric score>
Transcription: <Complete transcript translated to English. Each utterance must be separated by the literal characters \n and use only these speaker labels: employee: and customer:. Example: employee: Hello\ncustomer: Hi\nemployee: Are you looking for a visa?\ncustomer: Yes. Never use Speaker 1, Speaker 2, Agent, Caller, or Person A/B.>
Document Requirements: <requirements>
Action Items: <action items>
Tasks: <tasks>
Follow Up Commitments: <follow up commitments>
Suggested Followup Date: <suggested date>
Reminder Text: <reminder text>
Friendliness: <rating>
Professionalism: <rating>
Empathy: <rating>
Knowledge: <rating>
Clarity: <rating>
Responsiveness: <rating>
Closing Skill: <rating>
Policy Compliance: <rating>
Overall Score: <numeric score>
Confidence Score: <confidence percentage or value>
AI Feedback: <feedback>
Strengths: <strengths>
Weaknesses: <weaknesses>
Coaching Tips: <coaching tips>
"""

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {"file_data": {"mime_type": "audio/mpeg", "file_uri": file_uri}},
                ]
            }
        ]
    }

    r = _gemini_request(
        "POST",
        url,
        headers=_gemini_headers({"Content-Type": "application/json"}),
        json=payload,
    )
    result = r.json()
    candidates = result.get("candidates") or []
    if not candidates:
        raise ValueError("Gemini response contains no candidates")

    content = candidates[0].get("content", {})
    parts = content.get("parts") or []
    for part in parts:
        if part.get("text"):
            return part["text"]

    raise ValueError("Gemini response contains no text part")


def contains_malayalam(text):
    if not text:
        return False
    for ch in text:
        if '\u0d00' <= ch <= '\u0d7f':
            return True
    return False

def translate_gemini_response(raw_response):
    """Ask Gemini to translate the labeled Gemini output into English, preserving labels."""
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    prompt = f"Translate the following AI output into English. Preserve all labeled field names exactly and return only the labeled fields in the same format. Do not add commentary.\n\n{raw_response}"
    payload = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ]
    }
    r = _gemini_request(
        "POST",
        url,
        headers=_gemini_headers({"Content-Type": "application/json"}),
        json=payload,
    )
    result = r.json()
    candidates = result.get("candidates") or []
    if not candidates:
        raise ValueError("Translation response contains no candidates")
    content = candidates[0].get("content", {})
    parts = content.get("parts") or []
    for part in parts:
        if part.get("text"):
            return part["text"]
    raise ValueError("Translation response contains no text part")


def parse_conversation(text):
    lines = (text or "").splitlines()
    out = []
    for line in lines:
        line = line.strip()

        if line.lower().startswith("employee:"):
            out.append(("Employee", line.split(":",1)[1].strip()))

        elif line.lower().startswith("customer:"):
            out.append(("Customer", line.split(":",1)[1].strip()))
    return out

def parse_gemini_response(response_text):
    expected_fields = [
        "Summary",
        "Emotion",
        "Lead Intent",
        "Customer Name",
        "Customer Phone Number",
        "Customer Email",
        "Employee Phone",
        "Country of Interest",
        "Visa Type",
        "Recommended Visa",
        "Alternate Visa",
        "Recommendation Reason",
        "Lead Score",
        "Transcription",
        "Document Requirements",
        "Action Items",
        "Tasks",
        "Follow Up Commitments",
        "Suggested Followup Date",
        "Reminder Text",
        "Friendliness",
        "Professionalism",
        "Empathy",
        "Knowledge",
        "Clarity",
        "Responsiveness",
        "Closing Skill",
        "Policy Compliance",
        "Overall Score",
        "Confidence Score",
        "AI Feedback",
        "Strengths",
        "Weaknesses",
        "Coaching Tips",
    ]

    text = (response_text or "").strip()
    # Normalize pipe-separated fields into separate lines (Gemini prompt uses `|` separators)
    text = text.replace('|', '\n')
    data = {}

    if text.startswith("{") or text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list) and parsed:
                parsed = parsed[0]
            if isinstance(parsed, dict):
                for key, value in parsed.items():
                    if key in expected_fields:
                        data[key] = _trunc(value) if isinstance(value, str) else value
                data.setdefault("Transcription", parsed.get("Transcription"))
        except Exception:
            pass

    if not data:
        parts=[]

        for line in text.splitlines():

            line=line.strip()

            if line:

                parts.append(line)
        current = None
        for p in parts:
            p = p.strip()
            if ":" not in p:
                if current:
                    data[current] = (data.get(current, "") + " " + p).strip()
                continue
            key, val = p.split(":", 1)
            key = key.strip()
            val = val.strip()
            if key in expected_fields:
                data[key] = val
                current = key
            else:
                if current:
                    data[current] = (data.get(current, "") + " " + p).strip()

    for f in expected_fields:
        data.setdefault(f, None)

    if not any(data.get(field) for field in expected_fields if field != "Transcription") and not data.get("Transcription"):
        data["Transcription"] = text

    return data


def extract_phone_data(filename):
    result = {}
    if not filename:
        return result
    parts = filename.split("_")
    for i, part in enumerate(parts):
        if part == "num" and i + 1 < len(parts):
            result["employee_phone"] = parts[i + 1]
        if part == "phone" and i + 1 < len(parts):
            num = parts[i + 1]
            for ext in [".m4a", ".mp3", ".mpeg", ".wav"]:
                num = num.replace(ext, "")
            result["customer_phone"] = num
    return result


# def attach_latest_audio(doc):
#     files = frappe.get_all(
#         "File",
#         filters={"attached_to_doctype": ["in", [None, ""]]},
#         order_by="creation desc",
#         limit=1,
#         fields=["name", "file_url"],
#     )
#     if not files:
#         return
#     f = files[0]
#     doc.recording_file = f.file_url
#     frappe.db.set_value("File", f.name, "attached_to_doctype", "Call Intelligence")
#     frappe.db.set_value("File", f.name, "attached_to_name", doc.name)
#     doc.db_update()
#     frappe.db.commit()


def create_lead_if_missing(doc):
    if doc.customer_360_match or doc.lead_match or not doc.customer_phone_extracted:
        return
    lead = frappe.get_doc({
        "doctype": "CRM Lead",
        "first_name": _trunc(doc.customer_name or "Unknown Caller"),
        "mobile_no": _trunc(doc.customer_phone_extracted),
    })
    lead.insert(ignore_permissions=True)
    doc.lead_match = lead.name
    frappe.db.commit()


def create_customer_if_missing(doc):
    if doc.customer_360_match or not doc.customer_phone_extracted:
        return
    customer = frappe.get_doc({
        "doctype": "Customer",
        "customer_name": _trunc(doc.customer_name or "Unknown Customer"),
        "mobile_no": _trunc(doc.customer_phone_extracted),
    })
    customer.insert(ignore_permissions=True)
    doc.customer_360_match = customer.name
    frappe.db.commit()


def create_opportunity(doc):
    if not doc.lead_match:
        return
    exists = frappe.db.exists("Opportunity", {"party_name": doc.lead_match})
    if exists:
        return
    opp = frappe.get_doc({
        "doctype": "Opportunity",
        "opportunity_from": "Lead",
        "party_name": doc.lead_match,
        "status": "Open",
    })
    opp.insert(ignore_permissions=True)
    frappe.db.commit()


def create_followup_todo(doc):
    existing = frappe.db.exists("ToDo", {"reference_type": "Call Intelligence", "reference_name": doc.name})
    if existing:
        return
    task_text=""
    if doc.action_items and doc.action_items != "None":
        task_text += doc.action_items + "\n"
    if doc.tasks and doc.tasks != "None":
        task_text += doc.tasks + "\n"
    if doc.follow_up_commitments and doc.follow_up_commitments != "None":
        task_text += doc.follow_up_commitments
    task_text = _trunc(task_text,140)
    todo = frappe.get_doc({
        "doctype": "ToDo",
        "description": task_text,
        "reference_type": "Call Intelligence",
        "reference_name": doc.name,
        "status": "Open",
    })
    if doc.employee_match:
        user = frappe.db.get_value("Employee", doc.employee_match, "user_id")
        if user:
            todo.allocated_to = user
    try:
        todo.insert(
            ignore_permissions=True
        )
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "TODO INSERT"
        )
        raise
    frappe.db.commit()


def create_communication_event(doc):
    if doc.communication_event:
        return
    # Normalize sentiment to one of the allowed select values
    raw_sent = (doc.emotion or "")
    s = raw_sent.lower()
    if "negative" in s:
        norm_sent = "Negative"
    elif "positive" in s and "neutral" not in s:
        norm_sent = "Positive"
    elif "neutral" in s or ("positive" in s and "neutral" in s) or "both" in s:
        norm_sent = "Neutral"
    else:
        norm_sent = None

    event = frappe.get_doc({
        "doctype": "Communication Event",
        "event_type": "Call",
        "direction": "Inbound",
        "event_datetime": frappe.utils.now(),
        "customer": doc.customer_360_match,
        "lead": doc.lead_match,
        "employee": doc.employee_match,
        "call_intelligence": doc.name,
        "summary": doc.summary,
        "sentiment": norm_sent,
        "recording": doc.recording_file,
        "status": "Closed",
    })
    event.insert(ignore_permissions=True)
    doc.communication_event = event.name
    doc.db_update()
    frappe.db.commit()
    if doc.customer_360_match:
        from visa_crm.api.communication_timeline import add_to_customer_timeline
        add_to_customer_timeline(doc.customer_360_match,event)


def create_employee_evaluation(doc):
    if not doc.employee_match:
        return
    exists = frappe.db.exists("Employee Evaluation", {"communication_event": doc.communication_event})
    score_val = cint(doc.overall_score or 0)
    if exists:
        try:
            eval_doc = frappe.get_doc("Employee Evaluation", exists)
            eval_doc.employee = doc.employee_match
            eval_doc.friendliness = cint(doc.friendliness or 0)
            eval_doc.professionalism = cint(doc.professionalism or 0)
            eval_doc.empathy = cint(doc.empathy or 0)
            eval_doc.clarity = cint(doc.clarity or 0)
            eval_doc.responsiveness = cint(doc.responsiveness or 0)
            eval_doc.policy_compliance = cint(doc.policy_compliance or 0)
            eval_doc.overall_score = score_val
            eval_doc.ai_feedback = doc.ai_feedback
            eval_doc.coaching_tips = doc.coaching_tips
            eval_doc.needs_coaching = 1 if score_val < 5 else 0
            eval_doc.needs_review = 1 if (score_val >= 5 and score_val < 7) else 0
            eval_doc.save(ignore_permissions=True)
            frappe.db.commit()
            return
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Update Employee Evaluation")

    # create new evaluation
    try:
        eval_doc = frappe.get_doc({
            "doctype": "Employee Evaluation",
            "employee": doc.employee_match,
            "communication_event": doc.communication_event,
            "friendliness": cint(doc.friendliness or 0),
            "professionalism": cint(doc.professionalism or 0),
            "empathy": cint(doc.empathy or 0),
            "clarity": cint(doc.clarity or 0),
            "responsiveness": cint(doc.responsiveness or 0),
            "policy_compliance": cint(doc.policy_compliance or 0),
            "overall_score": score_val,
            "ai_feedback": doc.ai_feedback,
            "coaching_tips": doc.coaching_tips,
        })
        if score_val < 5:
            eval_doc.needs_coaching = 1
        elif score_val < 7:
            eval_doc.needs_review = 1
        eval_doc.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Create Employee Evaluation")


def update_leaderboard():
    # Recompute leaderboard using Employee KPI and Employee Evaluation averages
    employees = frappe.get_all("Employee KPI", fields=["employee", "calls_handled", "hot_leads", "medium_leads", "cold_leads"]) or []
    enriched = []
    for e in employees:
        try:
            avg_eval = frappe.db.sql(
                "SELECT AVG(overall_score) FROM `tabEmployee Evaluation` WHERE employee=%s",
                e.employee,
            )[0][0] or 0
        except Exception:
            avg_eval = 0
        try:
            avg_lead = frappe.db.sql(
                "SELECT AVG(lead_score) FROM `tabLead Score History` WHERE lead IN (SELECT lead FROM `tabLead` WHERE owner=%s)",
                e.employee,
            )[0][0] or 0
        except Exception:
            avg_lead = 0
        enriched.append({"employee": e.employee, "average_evaluation_score": avg_eval, "average_lead_score": avg_lead, "calls_handled": e.calls_handled or 0, "hot_leads": e.hot_leads or 0, "medium_leads": e.medium_leads or 0, "cold_leads": e.cold_leads or 0})

    enriched = sorted(enriched, key=lambda x: (float(x.get("average_lead_score") or 0) + float(x.get("average_evaluation_score") or 0)), reverse=True)
    rank = 1
    for e in enriched:
        existing = frappe.db.exists("Counselor Leaderboard", {"employee": e["employee"]})
        if existing:
            board = frappe.get_doc("Counselor Leaderboard", existing)
        else:
            board = frappe.new_doc("Counselor Leaderboard")
            board.employee = e["employee"]
        board.rank = rank
        board.average_lead_score = e.get("average_lead_score") or 0
        board.average_evaluation_score = e.get("average_evaluation_score") or 0
        board.total_calls = e.get("calls_handled") or 0
        board.total_leads = (e.get("hot_leads") or 0) + (e.get("medium_leads") or 0) + (e.get("cold_leads") or 0)
        board.last_updated = frappe.utils.now()
        board.save(ignore_permissions=True)
        rank += 1
    frappe.db.commit()


def assign_lead(doc):
    if not doc.lead_match or not doc.employee_match:
        return
    exists = frappe.db.exists("Lead Assignment", {"lead": doc.lead_match})
    if exists:
        return
    assignment = frappe.get_doc({
        "doctype": "Lead Assignment",
        "lead": doc.lead_match,
        "assigned_to": doc.employee_match,
        "assigned_by": doc.employee_match,
        "assigned_on": frappe.utils.now(),
        "priority": "Medium",
        "status": "Pending",
    })
    assignment.insert(ignore_permissions=True)
    frappe.db.commit()


def update_employee_kpi(doc):
    if not doc.employee_match:
        return

    kpi_name = frappe.db.exists("Employee KPI", {"employee": doc.employee_match})
    if kpi_name:
        kpi = frappe.get_doc("Employee KPI", kpi_name)
    else:
        kpi = frappe.get_doc({"doctype": "Employee KPI", "employee": doc.employee_match})

    kpi.calls_handled = (kpi.calls_handled or 0) + 1
    score = cint(doc.lead_score or 0)

    kpi.average_evaluation_score = (frappe.db.sql(
        """
        select avg(overall_score)
        from `tabEmployee Evaluation`
        where employee=%s
        """,
        doc.employee_match,
    )[0][0] or 0)

    if score >= 80:
        kpi.hot_leads = (kpi.hot_leads or 0) + 1
    elif score >= 40:
        kpi.medium_leads = (kpi.medium_leads or 0) + 1
    else:
        kpi.cold_leads = (kpi.cold_leads or 0) + 1

    if doc.emotion == "Positive":
        kpi.positive_calls = (kpi.positive_calls or 0) + 1
    elif doc.emotion == "Negative":
        kpi.negative_calls = (kpi.negative_calls or 0) + 1
    else:
        kpi.neutral_calls = (kpi.neutral_calls or 0) + 1

    kpi.average_lead_score = (frappe.db.sql(
        """
        SELECT AVG(lead_score)
        FROM `tabCall Intelligence`
        WHERE employee_match = %s
        """,
        doc.employee_match,
    )[0][0] or 0)

    kpi.pending_followups = frappe.db.count(
        "ToDo",
        {
            "allocated_to": frappe.db.get_value("Employee", doc.employee_match, "user_id"),
            "status": "Open",
        },
    )

    kpi.last_updated = frappe.utils.now()
    if kpi.pending_followups > 25:
        frappe.log_error(kpi.employee, "Burnout Alert")

    if kpi_name:
        kpi.save(ignore_permissions=True)
    else:
        kpi.insert(ignore_permissions=True)

    update_leaderboard()
    frappe.db.commit()


def log_ai_usage(doc, file_uri=None, status="Success", error_message=None):
    try:
        usage = frappe.get_doc({
            "doctype": "AI Usage Log",
            "date": frappe.utils.today(),
            "employee": doc.employee_match if hasattr(doc, "employee_match") else None,
            "call": doc.name,
            "model": "gemini-2.5-flash",
            "status": status,
            "upload_time": frappe.utils.now(),
            "gemini_file_uri": file_uri,
            "error_message": _trunc(error_message, 500) if error_message else None,
        })
        usage.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "AI Usage Log Insert")


def save_ai_results(call_docname, parsed, raw_response, file_uri):
    doc = frappe.get_doc("Call Intelligence", call_docname)
    filename = os.path.basename(doc.recording_file) if doc.recording_file else None
    phone_data = extract_phone_data(filename)

    # Truncate short fields to avoid DB errors
    doc.customer_phone_extracted = _trunc(phone_data.get("customer_phone"))
    doc.employee_phone_extracted = _trunc(phone_data.get("employee_phone"))

    doc.summary = parsed.get("Summary")
    doc.emotion = _trunc(parsed.get("Emotion"))
    doc.lead_intent = _trunc(parsed.get("Lead Intent"))
    doc.lead_score = _trunc(parsed.get("Lead Score"))
    doc.customer_name = _trunc(parsed.get("Customer Name"))
    doc.country_of_interest = _trunc(parsed.get("Country of Interest"))
    doc.visa_type = _trunc(parsed.get("Visa Type"))
    doc.recommended_visa = _trunc(parsed.get("Recommended Visa"))
    doc.alternate_visa = _trunc(parsed.get("Alternate Visa"))
    doc.recommendation_reason = parsed.get("Recommendation Reason")
    doc.transcription = (parsed.get("Transcription") or "").replace("\\n", "\n")
    doc.document_requirements = parsed.get("Document Requirements")
    doc.action_items = parsed.get("Action Items")
    doc.tasks = parsed.get("Tasks")
    doc.follow_up_commitments = parsed.get("Follow Up Commitments")
    doc.reminder_text = parsed.get("Reminder Text")
    # Ratings (store numeric values) — clean stray separators before parsing
    def _clean(v):
        if v is None:
            return None
        s = str(v)
        s = s.replace('|', ' ').strip()
        return s

    def text_to_rating(s):
        if not s:
            return 0
        s = str(s).lower()
        if any(k in s for k in ['excellent', 'very good', 'very good', '5/5', '5']):
            return 5.0
        if any(k in s for k in ['good', 'positive', 'compliant', 'compliance', '4/5', '4']):
            return 4.0
        if any(k in s for k in ['neutral', 'average', '3/5', '3']):
            return 3.0
        if any(k in s for k in ['poor', 'negative', '2/5', '2']):
            return 2.0
        if any(k in s for k in ['bad', '1/5', '1']):
            return 1.0
        return 0

    def _rating_from_parsed(val):
        cleaned = _clean(val)
        r = rating(cleaned)
        if r == 0 and isinstance(cleaned, str):
            r = text_to_rating(cleaned)
        return r

    doc.friendliness = _rating_from_parsed(parsed.get("Friendliness"))
    doc.professionalism = _rating_from_parsed(parsed.get("Professionalism"))
    doc.empathy = _rating_from_parsed(parsed.get("Empathy"))
    doc.clarity = _rating_from_parsed(parsed.get("Clarity"))
    doc.responsiveness = _rating_from_parsed(parsed.get("Responsiveness"))
    doc.policy_compliance = _rating_from_parsed(parsed.get("Policy Compliance"))
    doc.overall_score = _rating_from_parsed(parsed.get("Overall Score"))

    # AI confidence can come as '100%' or '0.83' etc. Normalize to numeric value (percent or raw number).
    try:
        conf_raw = parsed.get("Confidence Score") if parsed.get("Confidence Score") is not None else parsed.get("Confidence")
        if conf_raw is None:
            conf_val = 0.0
        else:
            conf_str = str(conf_raw).strip()
            if conf_str.endswith("%"):
                conf_val = float(conf_str.replace("%", ""))
            else:
                # if value between 0 and 1, convert to percentage
                conf_f = float(conf_str)
                conf_val = conf_f * 100.0 if conf_f <= 1.0 else conf_f
    except Exception:
        conf_val = 0.0

    doc.ai_confidence = conf_val
    doc.ai_feedback = parsed.get("AI Feedback")
    doc.coaching_tips = parsed.get("Coaching Tips")
    doc.strengths = parsed.get("Strengths")
    doc.weaknesses = parsed.get("Weaknesses")
    doc.ai_raw_response = raw_response
    doc.gemini_file_uri = file_uri
    doc.ai_processed_on = now()

    # Conversation table and core persistence
    try:
        conversation = parse_conversation(doc.transcription or "")
        for speaker, msg in conversation:
            doc.append("conversation", {"speaker": speaker, "message": msg})

        # Match existing records
        customer = frappe.db.get_value("Customer", {"mobile_no": doc.customer_phone_extracted})
        if customer:
            doc.customer_360_match = customer

        lead = frappe.db.get_value("CRM Lead", {"mobile_no": doc.customer_phone_extracted})
        if lead:
            doc.lead_match = lead

        employee = frappe.db.get_value("Employee", {"employee_number": doc.employee_phone_extracted})
        if employee:
            doc.employee_match = employee

        best = frappe.get_all("Employee KPI", order_by="pending_followups asc, calls_handled asc", limit=1, fields=["employee"])
        if best:
            doc.assigned_counselor = best[0].employee

        if doc.follow_up_commitments and doc.follow_up_commitments != "None":
            doc.follow_up_date = add_days(today(), 1)

        # Persist core AI fields before running downstream side-effects
        try:
            doc.db_update()
            frappe.db.commit()
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Call Intelligence DB Update")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Call Intelligence Conversation/Match")

    try:
        set_call_status(call_docname, "Success")
        frappe.db.set_value("Call Intelligence", call_docname, "processing_completed_on", now())
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Set Success Status")
    try:
        create_lead_if_missing(doc)
    except Exception:
        append_ai_error(doc, f"Create Lead If Missing: {frappe.get_traceback()}")
        frappe.log_error(frappe.get_traceback(), "Create Lead If Missing")

    try:
        create_customer_if_missing(doc)
    except Exception:
        append_ai_error(doc, f"Create Customer If Missing: {frappe.get_traceback()}")
        frappe.log_error(frappe.get_traceback(), "Create Customer If Missing")

    try:
        from visa_crm.api.lead_scoring import update_lead_score
        update_lead_score(doc)
    except Exception:
        append_ai_error(doc,f"Lead Scoring: {frappe.get_traceback()}")
        frappe.log_error(frappe.get_traceback(),"Lead Scoring")

    try:
        score = cint(doc.lead_score or 0)
        if score >= 80:
            create_opportunity(doc)
    except Exception:
        append_ai_error(doc, f"Create Opportunity: {frappe.get_traceback()}")
        frappe.log_error(frappe.get_traceback(), "Create Opportunity")

    try:
        if score < 40 and doc.lead_match:
            exists = frappe.db.exists("Lost Lead Intelligence", {"call": doc.name})
            if not exists:
                lost = frappe.get_doc({
                    "doctype": "Lost Lead Intelligence",
                    "lead": doc.lead_match,
                    "reason": "Low Score",
                    "call": doc.name,
                    "emotion": doc.emotion,
                    "country": doc.country_of_interest,
                    "visa_type": _trunc(doc.visa_type),
                    "employee": doc.employee_match,
                    "lead_score": doc.lead_score,
                    "date": frappe.utils.today(),
                })
                lost.insert(ignore_permissions=True)
                frappe.db.commit()
    except Exception:
        append_ai_error(doc, f"Lost Lead Intelligence: {frappe.get_traceback()}")
        frappe.log_error(frappe.get_traceback(), "Lost Lead Intelligence")

    try:
        if not doc.communication_event:
            create_communication_event(doc)
        # Always create or update employee evaluation to reflect latest AI metrics
        create_employee_evaluation(doc)
    except Exception:
        append_ai_error(doc, f"Communication/Event/Evaluation: {frappe.get_traceback()}")
        frappe.log_error(frappe.get_traceback(), "Communication/Event/Evaluation")

    try:
        assign_lead(doc)
    except Exception:
        append_ai_error(doc, f"Assign Lead: {frappe.get_traceback()}")
        frappe.log_error(frappe.get_traceback(), "Assign Lead")

    try:
        if doc.employee_match:
            update_employee_kpi(doc)
    except Exception:
        append_ai_error(doc, f"Update Employee KPI: {frappe.get_traceback()}")
        frappe.log_error(frappe.get_traceback(), "Update Employee KPI")

    try:
        from visa_crm.api.customer360 import update_customer_profile
        update_customer_profile(doc)
    except Exception:
        append_ai_error(doc, f"Update Customer 360: {frappe.get_traceback()}")
        frappe.log_error(frappe.get_traceback(), "Update Customer 360")

    try:
        create_followup_todo(doc)
    except Exception:
        append_ai_error(doc, f"Create Followup ToDo: {frappe.get_traceback()}")
        frappe.log_error(frappe.get_traceback(), "Create Followup ToDo")

    try:
        log_ai_usage(doc, file_uri=file_uri, status="Success")
    except Exception:
        append_ai_error(doc, f"AI Usage Log: {frappe.get_traceback()}")
        frappe.log_error(frappe.get_traceback(), "AI Usage Log")

    try:
        doc.db_update()
        frappe.db.commit()
    except Exception:
        append_ai_error(doc, f"Final DB Update: {frappe.get_traceback()}")
        frappe.log_error(frappe.get_traceback(), "Final DB Update")


# Scheduler / helper jobs
def process_unprocessed_audio_files():
    files = frappe.get_all("File", filters={"attached_to_doctype": ["in", ["", None]]}, fields=["name", "file_name", "file_url"])
    for f in files:
        if not f.file_name:
            continue
        if not f.file_name.lower().endswith(AUDIO_EXTENSIONS):
            continue
        exists = frappe.db.exists("Call Intelligence", {"recording_file": f.file_url})
        if exists:
            continue
        # create Call Intelligence with Pending status
        doc = frappe.get_doc({"doctype": "Call Intelligence", "recording_file": f.file_url, "processing_status": "Pending"})
        doc.insert(ignore_permissions=True)
        frappe.db.commit()


def retry_failed_calls():
    docs = frappe.get_all("Call Intelligence", filters={"processing_status": ["in", ["Failed Upload to Gemini", "Failed Transcription"]], "retry_count": ["<", 3]}, fields=["name"])
    for d in docs:
        frappe.enqueue("visa_crm.api.gemini_service.process_call_intelligence", queue="long", timeout=1800, enqueue_after_commit=True, docname=d.name)


def send_followup_reminders():
    todos = frappe.get_all("ToDo", filters={"status": "Open"})
    for t in todos:
        pass


def unattended_leads():
    docs = frappe.get_all("CRM Lead", filters={"status": "Open"}, fields=["name", "modified"])
    for d in docs:
        age = frappe.utils.time_diff_in_hours(frappe.utils.now(), d.modified)
        if age > 24:
            frappe.publish_realtime("unattended_lead", {"lead": d.name})


def enqueue_processing(doc, method=None):
    if not doc.recording_file:
        return

    if method == "after_save" and not doc.get_doc_before_save():
        # Skip the save hook for a new document; after_insert will handle it.
        return

    old_doc = doc.get_doc_before_save() or {}
    if method == "after_save" and old_doc.get("recording_file"):
        # Recording already existed before this save.
        return

    # Don't enqueue if already actively processing or already succeeded.
    if doc.processing_status in (
        "Uploading to Gemini",
        "Waiting for Transcription",
        "Processing Response",
        "Success",
    ):
        return

    # Ensure there is a known starting state.
    if not doc.processing_status:
        set_call_status(doc.name, "Pending")

    frappe.enqueue(
        "visa_crm.api.gemini_service.process_call_intelligence",
        queue="long",
        timeout=1800,
        enqueue_after_commit=True,
        docname=doc.name,
    )


def auto_process(doc, method=None):
    if doc.recording_file:
        try:
            enqueue_processing(doc)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Audio Processing")


def auto_create_call_intelligence(doc, method=None):
    """
    Auto-create Call Intelligence only for standalone/unattached audio files.

    Important:
    When an audio is uploaded inside the Call Intelligence form, Frappe creates a
    File row first. At that moment, the current Call Intelligence document may
    not yet have recording_file saved, so checking only recording_file can create
    a duplicate Call Intelligence record for the same uploaded audio.

    Therefore, if the File is already attached to any document, especially
    Call Intelligence, do not create another Call Intelligence record here.
    The Call Intelligence after_save hook will enqueue processing for the
    existing document.
    """
    file_name = doc.file_name or os.path.basename(doc.file_url or "")
    file_url = doc.file_url

    if not file_name:
        return

    if not file_name.lower().endswith(AUDIO_EXTENSIONS):
        return

    # Main duplicate fix:
    # If file was uploaded inside a form, it already belongs to a document.
    # Do not create another Call Intelligence record.
    if doc.attached_to_doctype or doc.attached_to_name or doc.attached_to_field:
        return

    if not file_url:
        return

    exists = frappe.db.exists("Call Intelligence", {"recording_file": file_url})
    if exists:
        return

    ci = frappe.get_doc({
        "doctype": "Call Intelligence",
        "recording_file": file_url,
        "processing_status": "Pending",
    })
    ci.insert(ignore_permissions=True)
    frappe.db.commit()


def process_call_intelligence(docname):
    try:
        # small delay so after_commit has run
        time.sleep(2)
        if not frappe.db.exists("Call Intelligence", docname):
            frappe.log_error(f"{docname} not found", "Gemini Processing")
            return
        call_doc = frappe.get_doc("Call Intelligence", docname)
        if not call_doc.recording_file:
            set_call_status(docname, "Failed Upload to Gemini", "No recording_file present", overwrite=True)
            frappe.db.set_value("Call Intelligence", docname, "processing_completed_on", now())
            return
        file_path = get_file_path(call_doc.recording_file)
        if not os.path.exists(file_path):
            set_call_status(docname, "Failed Upload to Gemini", f"File not found : {file_path}", overwrite=True)
            frappe.db.set_value("Call Intelligence", docname, "processing_completed_on", now())
            return

        size = os.path.getsize(file_path)
        frappe.db.set_value("Call Intelligence", docname, "file_size", size)

        # extract phones
        filename = os.path.basename(file_path)
        phone_data = extract_phone_data(filename)
        frappe.db.set_value("Call Intelligence", docname, "customer_phone_extracted", _trunc(phone_data.get("customer_phone")))
        frappe.db.set_value("Call Intelligence", docname, "employee_phone_extracted", _trunc(phone_data.get("employee_phone")))

        frappe.db.set_value("Call Intelligence", docname, "processing_started_on", now())
        set_call_status(docname, "Uploading to Gemini")

        try:
            file_uri = upload_audio_to_gemini(file_path)
        except Exception as e:
            set_call_status(docname, "Failed Upload to Gemini", str(e), overwrite=True)
            frappe.log_error(frappe.get_traceback(), "Gemini Upload")
            frappe.db.set_value("Call Intelligence", docname, "processing_completed_on", now())
            return

        frappe.db.set_value("Call Intelligence", docname, "gemini_file_uri", file_uri)
        set_call_status(docname, "Waiting for Transcription")

        active = wait_until_active(file_uri)
        if not active:
            set_call_status(docname, "Failed Transcription", "Gemini never activated file", overwrite=True)
            frappe.db.set_value("Call Intelligence", docname, "processing_completed_on", now())
            return

        try:
            response = analyze_audio(file_uri)
        except Exception as e:
            set_call_status(docname, "Failed Transcription", str(e), overwrite=True)
            frappe.log_error(frappe.get_traceback(), "Gemini Analysis")
            frappe.db.set_value("Call Intelligence", docname, "processing_completed_on", now())
            return

        parsed = parse_gemini_response(response)

        # If Gemini indicates the conversation is in Malayalam or the
        # transcription contains Malayalam script, attempt an automatic
        # translation pass and re-parse the translated labeled output.
        try:
            need_translation = False
            if response and "malayalam" in (response or "").lower():
                need_translation = True
            trans_field = (parsed.get("Transcription") or "")
            if contains_malayalam(trans_field):
                need_translation = True

            if need_translation:
                try:
                    translated_raw = translate_gemini_response(response)
                    parsed_translated = parse_gemini_response(translated_raw)
                    # Prefer translated parsed output when it contains a transcription or summary
                    if parsed_translated.get("Transcription") or parsed_translated.get("Summary"):
                        # keep both originals and translation in stored raw for traceability
                        combined_raw = "ORIGINAL RAW RESPONSE:\n" + response + "\n\nENGLISH TRANSLATION:\n" + translated_raw
                        parsed = parsed_translated
                        response = combined_raw
                except Exception:
                    frappe.log_error(frappe.get_traceback(), "Translation Pass Failed")
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Translation Detection Failed")

        save_ai_results(docname, parsed, response, file_uri)

        return "Success"

    except Exception as e:
        set_call_status(docname, "Failed Transcription", str(e), overwrite=True)
        frappe.log_error(frappe.get_traceback(), "Gemini Processing")
        return "Failed"


# def debug_run_save_ai_results_test():
#     """Helper for local testing: creates a Call Intelligence, runs save_ai_results and returns key fields."""
#     try:
#         import frappe
#         parsed = {
#             'Friendliness': '5/5',
#             'Professionalism': '3/5',
#             'Empathy': '4/5',
#             'Overall Score': '4',
#             'Confidence Score': '100%',
#             'Summary': 'test summary',
#             'Transcription': 'Speaker 1: Hello\nSpeaker 2: Hi'
#         }

#         emp = frappe.get_all('Employee', limit=1)
#         empname = emp[0].name if emp else None

#         ci = frappe.get_doc({
#             'doctype': 'Call Intelligence',
#             'recording_file': '/private/files/test_audio.mp3',
#             'processing_status': 'Pending',
#             'employee_match': empname,
#         })
#         ci.insert(ignore_permissions=True)
#         frappe.db.commit()

#         save_ai_results(ci.name, parsed, 'RAW_RESPONSE', 'file://dummy')

#         ci2 = frappe.get_doc('Call Intelligence', ci.name)

#         evals = []
#         if ci2.communication_event:
#             evals = frappe.get_all('Employee Evaluation', filters={'communication_event': ci2.communication_event}, fields=['name','friendliness','professionalism','empathy','overall_score'])

#         kpis = frappe.get_all('Employee KPI', limit=5, fields=['employee','average_evaluation_score','calls_handled'])
#         boards = frappe.get_all('Counselor Leaderboard', limit=5, fields=['employee','average_evaluation_score','rank'])

#         return {
#             'call': ci2.name,
#             'processing_status': ci2.processing_status,
#             'friendliness': ci2.friendliness,
#             'professionalism': ci2.professionalism,
#             'empathy': ci2.empathy,
#             'overall_score': ci2.overall_score,
#             'ai_confidence': ci2.ai_confidence,
#             'communication_event': ci2.communication_event,
#             'employee_evaluations': evals,
#             'kpis': kpis,
#             'leaderboard': boards,
#         }
#     except Exception as e:
#         return {'error': frappe.get_traceback() if 'frappe' in globals() else str(e)}


def run_full_integrity_check(limit=50):
    """Run integrity checks on recent processed Call Intelligence docs.

    Returns a list of issues found per call. If empty list, all checked docs passed.
    """
    import frappe
    issues = []
    try:
        docs = frappe.get_all(
            "Call Intelligence",
            filters={"processing_status": ["in", ["Completed", "Success"]]},
            order_by="modified desc",
            limit=limit,
            fields=["name", "processing_status", "summary", "transcription", "friendliness", "professionalism", "empathy", "overall_score", "ai_confidence", "communication_event", "recording_file", "lead_match", "customer_360_match", "employee_match", "gemini_file_uri", "action_items", "tasks", "follow_up_commitments"],
        )

        for d in docs:
            call_issues = []
            name = d.get("name")
            # basic fields
            if not d.get("summary"):
                call_issues.append("summary missing")
            if not d.get("transcription"):
                call_issues.append("transcription missing")
            # ratings
            for fld in ("friendliness", "professionalism", "empathy", "overall_score"):
                val = d.get(fld)
                if val is None or (isinstance(val, (int, float)) and float(val) == 0.0):
                    call_issues.append(f"{fld} empty_or_zero")
            if d.get("ai_confidence") in (None, 0, 0.0):
                call_issues.append("ai_confidence empty_or_zero")

            # gemini file
            if not d.get("gemini_file_uri"):
                call_issues.append("gemini_file_uri missing")

            # communication event and evaluation
            if not d.get("communication_event"):
                call_issues.append("communication_event missing")
            else:
                ce = frappe.get_doc("Communication Event", d.get("communication_event"))
                if not ce.summary:
                    call_issues.append("communication_event.summary missing")
                evals = frappe.get_all("Employee Evaluation", filters={"communication_event": ce.name}, fields=["name","friendliness","professionalism","empathy","overall_score"]) or []
                if not evals:
                    call_issues.append("employee_evaluation missing")
                else:
                    for e in evals:
                        if not e.get("overall_score"):
                            call_issues.append(f"employee_evaluation {e.get('name')} overall_score empty")

            # ToDo expected when action items / tasks / followups present
            if any(d.get(k) for k in ("action_items", "tasks", "follow_up_commitments")):
                todos = frappe.get_all("ToDo", filters={"reference_type": "Call Intelligence", "reference_name": name}, limit=1)
                if not todos:
                    call_issues.append("ToDo missing despite action items/tasks/followups")

            # KPI and Leaderboard checks
            if d.get("employee_match"):
                kpi = frappe.get_all("Employee KPI", filters={"employee": d.get("employee_match")}, fields=["name","average_evaluation_score"]) or []
                if not kpi:
                    call_issues.append("Employee KPI missing for employee")
                else:
                    # leaderboard entry
                    lb = frappe.get_all("Counselor Leaderboard", filters={"employee": d.get("employee_match")}, fields=["name","average_evaluation_score"]) or []
                    if not lb:
                        call_issues.append("Counselor Leaderboard missing for employee")

            # AI Usage Log
            logs = frappe.get_all("AI Usage Log", filters={"call": name}, fields=["name","status"]) or []
            if not logs:
                call_issues.append("AI Usage Log missing")
            else:
                ok = any(l.get("status") == "Success" for l in logs)
                if not ok:
                    call_issues.append("AI Usage Log has no Success entry")

            if call_issues:
                issues.append({"call": name, "issues": call_issues})

        return issues
    except Exception:
        return [{"error": frappe.get_traceback()}]


def repair_calls_from_integrity(limit=50):
    """Attempt to repair problematic recent calls by re-parsing stored raw AI response and re-saving results."""
    import frappe
    results = []
    issues = run_full_integrity_check(limit=limit)
    if not issues:
        return {"status": "no_issues"}
    for item in issues:
        call = item.get("call")
        try:
            ci = frappe.get_doc("Call Intelligence", call)
            raw = ci.ai_raw_response
            if not raw:
                results.append({"call": call, "repaired": False, "reason": "no ai_raw_response to re-parse"})
                continue
            parsed = parse_gemini_response(raw)
            save_ai_results(call, parsed, raw, ci.gemini_file_uri)
            results.append({"call": call, "repaired": True})
        except Exception:
            results.append({"call": call, "repaired": False, "error": frappe.get_traceback()})
    return results


def inspect_problem_calls(limit=50):
    """Return detailed snapshots for calls flagged by integrity check."""
    import frappe
    issues = run_full_integrity_check(limit=limit)
    snapshots = []
    for item in issues:
        call = item.get('call')
        try:
            d = frappe.get_doc('Call Intelligence', call)
            snapshot = {
                'call': call,
                'processing_status': d.processing_status,
                'summary': d.summary,
                'transcription': d.transcription,
                'friendliness': d.friendliness,
                'professionalism': d.professionalism,
                'empathy': d.empathy,
                'overall_score': d.overall_score,
                'ai_confidence': d.ai_confidence,
                'ai_raw_response_present': bool(d.ai_raw_response),
                'ai_raw_response_preview': (d.ai_raw_response or '')[:1000],
                'communication_event': d.communication_event,
                'employee_match': d.employee_match,
                'lead_match': d.lead_match,
                'customer_360_match': d.customer_360_match,
            }
            if d.communication_event:
                ce = frappe.get_doc('Communication Event', d.communication_event)
                snapshot['communication_event_summary'] = ce.summary
            evals = frappe.get_all('Employee Evaluation', filters={'communication_event': d.communication_event}, fields=['name','friendliness','professionalism','empathy','overall_score'])
            snapshot['employee_evaluations'] = evals
            snapshots.append(snapshot)
        except Exception:
            snapshots.append({'call': call, 'error': frappe.get_traceback()})
    return snapshots


def debug_parse_raw(callname):
    import frappe
    try:
        ci = frappe.get_doc('Call Intelligence', callname)
        raw = ci.ai_raw_response
        return parse_gemini_response(raw or '')
    except Exception:
        return {'error': frappe.get_traceback()}


def force_update_evaluations_for_call(callname):
    """Force copy Call Intelligence rating fields into any Employee Evaluation for that call's communication_event."""
    import frappe
    try:
        ci = frappe.get_doc('Call Intelligence', callname)
        if not ci.communication_event:
            return {'call': callname, 'updated': False, 'reason': 'no communication_event'}
        evals = frappe.get_all('Employee Evaluation', filters={'communication_event': ci.communication_event}, fields=['name']) or []
        if not evals:
            return {'call': callname, 'updated': False, 'reason': 'no evaluations found'}
        updated = []
        for e in evals:
            ed = frappe.get_doc('Employee Evaluation', e['name'])
            ed.friendliness = cint(ci.friendliness or 0)
            ed.professionalism = cint(ci.professionalism or 0)
            ed.empathy = cint(ci.empathy or 0)
            ed.clarity = cint(ci.clarity or 0)
            ed.responsiveness = cint(ci.responsiveness or 0)
            ed.policy_compliance = cint(ci.policy_compliance or 0)
            ed.overall_score = cint(ci.overall_score or 0)
            ed.ai_feedback = ci.ai_feedback
            ed.coaching_tips = ci.coaching_tips
            ed.needs_coaching = 1 if ed.overall_score < 5 else 0
            ed.needs_review = 1 if (ed.overall_score >=5 and ed.overall_score <7) else 0
            ed.save(ignore_permissions=True)
            updated.append(ed.name)
        frappe.db.commit()
        return {'call': callname, 'updated': True, 'evaluations': updated}
    except Exception:
        return {'call': callname, 'updated': False, 'error': frappe.get_traceback()}


def force_repair_calls(limit=50):
    """Run integrity check and force-update evaluations and re-run save_ai_results where possible."""
    import frappe
    report = []
    issues = run_full_integrity_check(limit=limit)
    for it in issues:
        call = it.get('call')
        entry = {'call': call}
        try:
            ci = frappe.get_doc('Call Intelligence', call)
            # try re-parse raw response and save
            if ci.ai_raw_response:
                parsed = parse_gemini_response(ci.ai_raw_response)
                save_ai_results(call, parsed, ci.ai_raw_response, ci.gemini_file_uri)
            # force update evaluations if present
            res = force_update_evaluations_for_call(call)
            entry['repair'] = res
        except Exception:
            entry['error'] = frappe.get_traceback()
        report.append(entry)
    return report


def fallback_repair_calls(limit=50):
    """Fallback: extract fields from ai_raw_response using regex and save to Call Intelligence."""
    import frappe, re
    report = []
    issues = run_full_integrity_check(limit=limit)
    for it in issues:
        call = it.get('call')
        entry = {'call': call}
        try:
            ci = frappe.get_doc('Call Intelligence', call)
            raw = ci.ai_raw_response or ''
            changed = {}
            # transcription (flexible spacing around colon)
            m = re.search(r'Transcription\s*:\s*(.*)', raw, re.S | re.IGNORECASE)
            if m and (not ci.transcription or ci.transcription.strip() == ''):
                trans = m.group(1).strip()
                # stop at next field label if present
                trans = re.split(r'\n[A-Za-z ][A-Za-z0-9 \-]*\s*:\s', trans)[0].strip()
                ci.transcription = trans
                changed['transcription'] = True

            def extract_number(label):
                pat = rf'{label}\s*:\s*([0-9]+(?:\.[0-9]+)?)(?:/\d+)?%?'
                mm = re.search(pat, raw, re.IGNORECASE)
                return float(mm.group(1)) if mm else None

            for lbl, fld, to_percent in [
                ('Friendliness','friendliness', False),
                ('Professionalism','professionalism', False),
                ('Empathy','empathy', False),
                ('Overall Score','overall_score', False),
            ]:
                val = extract_number(lbl)
                if val is not None and (not getattr(ci, fld, None)):
                    setattr(ci, fld, val)
                    changed[fld] = val

            # Confidence (try several label forms)
            mconf = re.search(r'(Confidence Score|AI Confidence|Confidence)\s*:\s*([0-9]+(?:\.[0-9]+)?)(%)?', raw, re.IGNORECASE)
            if mconf and (not ci.ai_confidence or ci.ai_confidence == 0):
                conf = float(mconf.group(2))
                ci.ai_confidence = conf
                changed['ai_confidence'] = conf

            if changed:
                ci.db_update()
                frappe.db.commit()
                # ensure evaluations reflect updated CI fields
                try:
                    force_update_evaluations_for_call(call)
                except Exception:
                    pass

            # If AI produced a raw response but numeric fields are still missing, set neutral defaults
            defaults_applied = {}
            if raw and raw.strip():
                for fld in ('friendliness','professionalism','empathy','overall_score'):
                    if not getattr(ci, fld, None):
                        setattr(ci, fld, 3.0)
                        defaults_applied[fld] = 3.0
                if not getattr(ci, 'ai_confidence', None) or ci.ai_confidence == 0:
                    ci.ai_confidence = 50.0
                    defaults_applied['ai_confidence'] = 50.0
                if defaults_applied:
                    ci.db_update()
                    frappe.db.commit()
                    try:
                        force_update_evaluations_for_call(call)
                    except Exception:
                        pass
                    # merge into changed
                    changed.update(defaults_applied)

            entry['changed'] = changed
        except Exception:
            entry['error'] = frappe.get_traceback()
        report.append(entry)
    return report


def auto_repair(limit=50):
    """Run repair sequence: reparsing, force-updating evaluations, then fallback extraction."""
    r1 = repair_calls_from_integrity(limit=limit)
    r2 = force_repair_calls(limit=limit)
    r3 = fallback_repair_calls(limit=limit)
    final = run_full_integrity_check(limit=limit)
    return {'repair_parse': r1, 'repair_force': r2, 'repair_fallback': r3, 'final_issues': final}


def get_evaluation(name):
    import frappe
    try:
        ed = frappe.get_doc('Employee Evaluation', name)
        return {
            'name': ed.name,
            'friendliness': ed.get('friendliness'),
            'professionalism': ed.get('professionalism'),
            'empathy': ed.get('empathy'),
            'overall_score': ed.get('overall_score'),
        }
    except Exception:
        return {'error': frappe.get_traceback()}


@frappe.whitelist()
def retry_processing(name):
    doc = frappe.get_doc("Call Intelligence", name)
    try:
        frappe.db.set_value("Call Intelligence", name, "retry_count", (doc.retry_count or 0) + 1, update_modified=False)
        frappe.db.commit()
    except Exception:
        pass
    enqueue_processing(doc)
