import frappe
import requests
import json
from frappe.utils.file_manager import get_file_path
from frappe.utils import cint


def _trunc(value, length=255):
    if not value:
        return value
    return str(value)[:length]


def get_api_key():
    settings = frappe.get_single("Gemini Settings")
    return settings.get_password("gemini_api_key")


def upload_audio_to_gemini(file_path):

    api_key = get_api_key()

    upload_url = (
        f"https://generativelanguage.googleapis.com/upload/v1beta/files"
        f"?key={api_key}"
    )

    filename = file_path.split("/")[-1]

    headers = {
        "X-Goog-Upload-Protocol": "raw",
        "X-Goog-Upload-File-Name": filename,
        "Content-Type": "audio/mpeg"
    }

    with open(file_path, "rb") as audio_file:
        response = requests.post(
            upload_url,
            headers=headers,
            data=audio_file
        )

    response.raise_for_status()

    result = response.json()
    upload_result = upload_audio_to_gemini(

        file_path

    )

    file_uri = upload_result["file"]["uri"]


    call_doc.gemini_upload_response = json.dumps(

        upload_result,

        indent=2

    )
    return result["file"]["uri"]


def analyze_audio(file_uri):

    api_key = get_api_key()

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={api_key}"
    )

    prompt = """
Analyze the audio conversation and translate all Malayalam or mixed Malayalam-English speech into professional English.

Identify speakers as Speaker 1, Speaker 2, Speaker 3, etc.

Return ONLY plain text.

Do not return JSON, markdown, code blocks, explanations, notes, or any text outside the specified format.

Translate the entire conversation into English.

Preserve the exact conversation order.

Generate a concise summary.

Determine emotion as Positive, Negative, or Neutral.

Determine Lead Intent.
Determine Lead Score from 0 to 100.
Give 3 coaching suggestions.
Give 3 weaknesses.
Give 3 strengths.
Mention exact dialogue snippets.
Lead Score:
0-20 = No Interest
21-40 = Low Interest
41-60 = Medium Interest
61-80 = High Interest
81-100 = Very Hot Lead
Extract Customer Name.
Extract Country of Interest.
Extract Visa Type.
Recommend best visa category.
Recommend alternate visa.
Explain reason.
Extract Document Requirements.
Extract Action Items.
Extract Tasks.
Extract Follow Up Commitments.
Suggest followup date.
Suggest reminder text.
Extract Customer Phone Number if mentioned.
Extract Customer Email.
Extract Employee Phone Number.
Estimate Lead Score from 0-100.
Evaluate employee.
Friendliness
Professionalism
Empathy
Clarity
Policy Compliance
Closing Skill
Calculate
Overall Score
Return coaching suggestions.
Give exactly three strengths.
Give exactly three weaknesses.
Give exactly three coaching tips.
Mention dialogue examples if possible.
Knowledge
Responsiveness
Closing Skill
Score each 0 to 10
Return feedback.
Return as:

Summary: xxx |
Emotion: xxx |
Lead Intent: xxx |
Lead Score: xxx |
Customer Name: xxx |
Country of Interest: xxx |
Visa Type: xxx |
Conversation:
Speaker 1 : xxx
Speaker 2 : xxx |
Transcription : xxx |
Document Requirements: xxx |
Action Items: xxx |
Tasks: xxx |
Follow Up Commitments: xxx |
Customer Phone Number: xxx |
Customer Email: xxx |
Employee Phone: xxx |
Friendliness : x |
Professionalism : x |
Empathy : x |
Clarity : x |
Responsiveness : x |
Policy Compliance : x |
Closing Skill : x |
Overall Score : x |
Confidence Score : x |
AI Feedback : xxx |
Coaching Tips : xxx |
"""

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    },
                    {
                        "file_data": {
                            "mime_type": "audio/mpeg",
                            "file_uri": file_uri
                        }
                    }
                ]
            }
        ]
    }

    response = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json=payload
    )

    response.raise_for_status()

    result = response.json()

    return result["candidates"][0]["content"]["parts"][0]["text"]

def parse_conversation(text):


    lines=text.split("\n")


    result=[]


    for line in lines:


        if "Speaker" in line:


            speaker,msg = line.split(

                ":",

                1

            )


            result.append(

                (

                    speaker.strip(),

                    msg.strip()

                )

            )


    return result

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
        "Reminder Text"
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
        "Coaching Tips"

    ]

    data = {}

    current_key = None

    parts = response_text.split("|")

    for part in parts:

        part = part.strip()

        matched = False

        for field in expected_fields:

            if ":" not in part:
                continue

            key, value = part.split(":", 1)

            key = key.strip()
            value = value.strip()

            if key == field:

                data[field] = value

                current_key = field

                matched = True

                break


        if not matched and current_key:

            data[current_key] = (

                data.get(current_key, "")

                + " "

                + part

            ).strip()


    for field in expected_fields:

        if field not in data:

            data[field] = None


    return data

def create_lead_if_missing(doc):

    if doc.customer_360_match:
        return

    if doc.lead_match:
        return

    if not doc.customer_phone_extracted:
        return

    lead = frappe.get_doc({
        "doctype": "CRM Lead",
        "first_name": doc.customer_name or "Unknown Caller",
        "mobile_no": doc.customer_phone_extracted
    })

    lead.insert(ignore_permissions=True)

    doc.lead_match = lead.name

    frappe.db.commit()

def create_customer_if_missing(doc):

    if doc.customer_360_match:
        return

    if not doc.customer_phone_extracted:
        return


    customer = frappe.get_doc(

        {

            "doctype":"Customer",

            "customer_name":

            doc.customer_name or "Unknown Customer",


            "mobile_no":

            doc.customer_phone_extracted


        }

    )


    customer.insert(

        ignore_permissions=True

    )


    doc.customer_360_match = (

        customer.name

    )


    frappe.db.commit()

def create_opportunity(doc):



    if not doc.lead_match:

        return



    exists = frappe.db.exists(

        "Opportunity",

        {

            "party_name":

            doc.lead_match

        }

    )



    if exists:

        return




    opp = frappe.get_doc(


        {


            "doctype":"Opportunity",


            "opportunity_from":"Lead",


            "party_name":

            doc.lead_match,


            "status":"Open"


        }


    )



    opp.insert(


        ignore_permissions=True


    )


    frappe.db.commit()

def create_followup_todo(doc):

    existing = frappe.db.exists(
        "ToDo",
        {
            "reference_type": "Call Intelligence",
            "reference_name": doc.name
        }
    )

    if existing:
        return

    task_text = ""
    if doc.action_items and doc.action_items != "None":
        task_text += doc.action_items + "\n"
    if doc.tasks and doc.tasks != "None":
        task_text += doc.tasks + "\n"
    if doc.follow_up_commitments and doc.follow_up_commitments != "None":
        task_text += doc.follow_up_commitments

    todo = frappe.get_doc(
        {
            "doctype": "ToDo",
            "description": task_text,
            "reference_type": "Call Intelligence",
            "reference_name": doc.name,
            "status": "Open"
        }
    )

    if doc.employee_match:
        user = frappe.db.get_value(
            "Employee",
            doc.employee_match,
            "user_id"
        )
        if user:
            todo.allocated_to = user

    todo.insert(ignore_permissions=True)

    frappe.db.commit()


def extract_phone_data(filename):

    result = {}

    parts = filename.split("_")

    for i, part in enumerate(parts):

        if part == "num" and i + 1 < len(parts):
            result["employee_phone"] = parts[i + 1]

        if part == "phone" and i + 1 < len(parts):
            result["customer_phone"] = (
                parts[i + 1]
                .replace(".m4a", "")
            )

    return result


def attach_latest_audio(doc):

    files = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": ["in", [None, ""]]
        },
        order_by="creation desc",
        limit=1,
        fields=[
            "name",
            "file_url"
        ]
    )

    if not files:
        return

    file = files[0]

    if not file:
        return

    doc.recording_file = file.file_url

    frappe.db.set_value(
        "File",
        file.name,
        "attached_to_doctype",
        "Call Intelligence"
    )

    frappe.db.set_value(
        "File",
        file.name,
        "attached_to_name",
        doc.name
    )

    doc.db_update()
    frappe.db.commit()


def create_lead_if_missing(doc):

    if doc.customer_360_match:
        return

    if doc.lead_match:
        return

    if not doc.customer_phone_extracted:
        return

    lead = frappe.get_doc({
        "doctype": "CRM Lead",
        "first_name": doc.customer_name or "Unknown Caller",
        "mobile_no": doc.customer_phone_extracted
    })

    lead.insert(ignore_permissions=True)

    doc.lead_match = lead.name

    frappe.db.commit()


def save_ai_results(call_docname, parsed, raw_response, file_uri):

    import frappe
    import os

    from frappe.utils import (
        now,
        add_days,
        today
    )

    doc = frappe.get_doc(
        "Call Intelligence",
        call_docname
    )

    filename = os.path.basename(
        doc.recording_file
    )

    phone_data = extract_phone_data(
        filename
    )

    doc.customer_phone_extracted = (
        phone_data.get("customer_phone")
    )

    doc.employee_phone_extracted = (
        phone_data.get("employee_phone")
    )

    doc.summary = parsed.get("Summary")
    doc.emotion = parsed.get("Emotion")
    doc.lead_intent = parsed.get("Lead Intent")
    doc.lead_score = parsed.get("Lead Score")
    doc.ai_confidence = parsed.get("Confidence Score")
    doc.customer_name = parsed.get("Customer Name")
    doc.country_of_interest = parsed.get("Country of Interest")

    doc.visa_type = parsed.get("Visa Type")
    doc.recommended_visa = parsed.get(
    "Recommended Visa"
    )
    doc.alternate_visa = parsed.get(
    "Alternate Visa"
    )
    doc.recommendation_reason = parsed.get(
    "Recommendation Reason"
    )    
    doc.transcription = parsed.get("Transcription")
    conversation = parse_conversation(
            doc.transcription or ""
    )
    for speaker,msg in conversation:
            doc.append(

                "conversation",

                {

                    "speaker":speaker,


                    "message":msg

                }

            )
    doc.document_requirements = parsed.get(
        "Document Requirements"
    )

    doc.action_items = parsed.get(
        "Action Items"
    )

    doc.tasks = parsed.get(
        "Tasks"
    )

    doc.follow_up_commitments = parsed.get(
        "Follow Up Commitments"
    )
    doc.reminder_text = parsed.get("Reminder Text")
    doc.friendliness = parsed.get(
        "Friendliness"
    )

    doc.professionalism = parsed.get(
        "Professionalism"
    )

    doc.empathy = parsed.get(
        "Empathy"
    )

    doc.clarity = parsed.get(
        "Clarity"
    )

    doc.responsiveness = parsed.get(
        "Responsiveness"
    )

    doc.policy_compliance = parsed.get(
        "Policy Compliance"
    )

    doc.overall_score = parsed.get(
        "Overall Score"
    )

    doc.ai_feedback = parsed.get(
        "AI Feedback"
    )

    doc.coaching_tips = parsed.get(
        "Coaching Tips"
    )
    
    doc.strengths = parsed.get(
            "Strengths"
    )
    doc.weaknesses = parsed.get(
            "Weaknesses"
    )
    doc.ai_raw_response = raw_response
    log_ai_usage(doc)

    doc.gemini_file_uri = file_uri

    doc.processing_status = "Completed"

    doc.ai_processed_on = now()

    usage = frappe.get_doc({

    "doctype":"AI Usage Log",

    "call":doc.name,

    "model":"gemini-2.5-flash",

    "status":"Success",

    "upload_time":doc.ai_processed_on,

    "gemini_file_uri":file_uri

    })

    usage.insert(ignore_permissions=True)
    customer = frappe.db.get_value(

        "Customer",

        {
            "mobile_no":
            doc.customer_phone_extracted
        }

    )

    if customer:

        doc.customer_360_match = customer



    lead = frappe.db.get_value(

        "CRM Lead",

        {
            "mobile_no":
            doc.customer_phone_extracted
        }

    )

    if lead:

        doc.lead_match = lead



    employee = frappe.db.get_value(

        "Employee",

        {
            "employee_number":
            doc.employee_phone_extracted
        }

    )

    if employee:

        doc.employee_match = employee

    best = frappe.get_all(

        "Employee KPI",

        order_by="pending_followups asc, calls_handled asc",

        limit=1,

        fields=[

            "employee"

        ]

    )


    if best:

        doc.assigned_counselor = (

            best[0].employee

        )


    if (

        doc.follow_up_commitments

        and

        doc.follow_up_commitments != "None"

    ):

        doc.follow_up_date = add_days(

            today(),

            1

        )



    create_lead_if_missing(doc)

    create_customer_if_missing(doc)

    if doc.lead_match:


        exists = frappe.db.exists(

            "Lead Score History",

            {

                "call_intelligence":

                doc.name

            }

        )


        if not exists:


            score_doc = frappe.get_doc(

                {

                    "doctype":

                    "Lead Score History",

                    "lead":

                    doc.lead_match,

                    "score":

                    doc.lead_score,

                    "emotion":

                    doc.emotion,

                    "intent":

                    doc.lead_intent,

                    "call_intelligence":

                    doc.name

                }

            )

            score_doc.insert(

                ignore_permissions=True

            )



    score = cint(

        doc.lead_score or 0

    )

    if score >= 80:


        create_opportunity(

            doc

        )


    if score < 40 and doc.lead_match:


        exists = frappe.db.exists(

            "Lost Lead Intelligence",

            {

                "call":

                doc.name

            }

        )


        if not exists:



            lost=frappe.get_doc({
            "doctype":"Lost Lead Intelligence",
            "lead":doc.lead_match,
            "reason":"Low Score",
            "call":doc.name,
            "emotion":doc.emotion,
            "country":doc.country_of_interest,
            "visa_type":doc.visa_type,
            "employee":doc.employee_match,
            "lead_score":doc.lead_score,
            "date":frappe.utils.today()
            })

            lost.insert(

                ignore_permissions=True

            )


            frappe.db.commit()



    if not doc.communication_event:


        create_communication_event(

            doc

        )


        create_employee_evaluation(

            doc

        )



    assign_lead(

        doc

    )



    if doc.employee_match:


        update_employee_kpi(

            doc

        )



    update_customer_360(

        doc

    )



    create_followup_todo(

        doc

    )



    doc.db_update()
    frappe.db.commit()



    frappe.db.commit()


def create_communication_event(doc):

    import frappe

    if doc.communication_event:
        return


    event = frappe.get_doc(

        {

            "doctype": "Communication Event",

            "event_type": "Call",

            "direction": "Inbound",

            "event_datetime": frappe.utils.now(),

            "customer": doc.customer_360_match,

            "lead": doc.lead_match,

            "employee": doc.employee_match,

            "call_intelligence": doc.name,

            "summary": doc.summary,

            "sentiment": doc.emotion,

            "recording": doc.recording_file,

            "status": "Closed"

        }

    )


    event.insert(

        ignore_permissions=True

    )


    doc.communication_event = event.name


    doc.db_update()
    frappe.db.commit()


    if doc.customer_360_match:


        customer_doc = frappe.get_doc(

            "Customer",

            doc.customer_360_match

        )


        meta = frappe.get_meta(

            "Customer"

        )


        if meta.has_field(

            "communication_timeline"

        ):


            customer_doc.append(

                "communication_timeline",

                {

                    "event_datetime":

                    event.event_datetime,


                    "communication_event":

                    event.name,


                    "summary":

                    event.summary,


                    "sentiment":

                    event.sentiment,


                    "employee":

                    event.employee,


                    "call_intelligence":

                    doc.name

                }

            )


            customer_doc.save(

                ignore_permissions=True

            )


    frappe.db.commit()

def create_employee_evaluation(doc):

    if not doc.employee_match:
        return

    exists = frappe.db.exists(
        "Employee Evaluation",
        {"communication_event": doc.communication_event}
    )

    if exists:
        return

    evaluation = frappe.get_doc(
        {
            "doctype": "Employee Evaluation",
            "employee": doc.employee_match,
            "communication_event": doc.communication_event,
            "friendliness": doc.friendliness or 0,
            "professionalism": doc.professionalism or 0,
            "empathy": doc.empathy or 0,
            "clarity": doc.clarity or 0,
            "responsiveness": doc.responsiveness or 0,
            "policy_compliance": doc.policy_compliance or 0,
            "overall_score": doc.overall_score or 0,
            "ai_feedback": doc.ai_feedback,
            "coaching_tips": doc.coaching_tips
        }
    )

    if doc.overall_score:
        score=cint(doc.overall_score)
    if score<5:
        evaluation.needs_coaching=1
    elif score<7:
        evaluation.needs_review=1
    evaluation.insert(ignore_permissions=True)
    frappe.db.commit()


def update_leaderboard():

    employees = frappe.get_all(
        "Employee KPI",
        fields=["*"]
    )

    employees = sorted(

        employees,

        key=lambda x: (

            (x.average_lead_score or 0)

            +

            (x.average_evaluation_score or 0)

        ),

        reverse=True

    )

    rank = 1

    for e in employees:

        existing = frappe.db.exists(

            "Counselor Leaderboard",

            {"employee": e.employee}

        )

        if existing:

            board = frappe.get_doc(

                "Counselor Leaderboard",

                existing

            )

        else:

            board = frappe.new_doc(

                "Counselor Leaderboard"

            )

            board.employee = e.employee


        board.rank = rank

        board.average_lead_score = (

            e.average_lead_score or 0

        )

        board.average_evaluation_score = (

            e.average_evaluation_score or 0

        )

        board.total_calls = (

            e.calls_handled or 0

        )

        board.total_leads = (

            (e.hot_leads or 0)

            +

            (e.medium_leads or 0)

            +

            (e.cold_leads or 0)

        )

        board.last_updated = frappe.utils.now()

        board.save(

            ignore_permissions=True

        )

        rank += 1


    frappe.db.commit()


def assign_lead(doc):

    if not doc.lead_match:
        return

    # FIX 6: Guard against None employee_match before creating assignment.
    if not doc.employee_match:
        return

    # FIX (original): exists check was placed after an early return, making it
    # unreachable. Now correctly placed after both guard checks.
    exists = frappe.db.exists(
        "Lead Assignment",
        {"lead": doc.lead_match}
    )

    if exists:
        return

    assignment = frappe.get_doc({
        "doctype": "Lead Assignment",
        "lead": doc.lead_match,
        "assigned_to": doc.employee_match,
        "assigned_by": doc.employee_match,
        "assigned_on": frappe.utils.now(),
        "priority": "Medium",
        "status": "Pending"
    })

    assignment.insert(ignore_permissions=True)
    frappe.db.commit()


def auto_process(doc, method=None):

    attach_latest_audio(doc)

    if doc.recording_file:
        try:
            process_call_intelligence(doc.name)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "Audio Processing"
            )

def enqueue_processing(doc,method=None):


    if not doc.recording_file:
        return


    if doc.processing_status=="Completed":
        return


    frappe.enqueue(

        "visa_crm.api.gemini_service.process_call_intelligence",

        queue="long",

        timeout=1800,

        enqueue_after_commit=True,

        docname=doc.name

    )


    
def process_call_intelligence(docname):

    import frappe
    import os

    response = None

    if not frappe.db.exists(
        "Call Intelligence",
        docname
    ):
        frappe.log_error(
            f"{docname} not found",
            "Gemini Processing"
        )
        return "Failed"

    call_doc = frappe.get_doc(
        "Call Intelligence",
        docname
    )

    if not call_doc.recording_file:
        return "Failed"

    try:

        file_path = get_file_path(
            call_doc.recording_file
        )

        filename = os.path.basename(
            file_path
        )

        size = os.path.getsize(
            file_path
        )

        call_doc.file_size = size

        phone_data = extract_phone_data(
            filename
        )

        call_doc.customer_phone_extracted = (
            phone_data.get(
                "customer_phone"
            )
        )

        call_doc.employee_phone_extracted = (
            phone_data.get(
                "employee_phone"
            )
        )
        call_doc.db_set(

            "processing_status",

            "Uploading to Gemini",

            commit=True

        )

        call_doc.db_set(

            "processing_status",

            "Uploading to Gemini",

            commit=True

        )

        frappe.db.commit()


        try:

            file_uri = (
                upload_audio_to_gemini(
                    file_path
                )
            )

        except Exception as e:

            call_doc.processing_status = (
                "Failed to Upload"
            )

            call_doc.retry_count = (
                call_doc.retry_count or 0
            ) + 1

            # record ai_error instead of writing to non-existent last_error
            frappe.db.set_value("Call Intelligence", docname, "ai_error", _trunc(str(e), 1000))
            call_doc.db_set(
                "processing_status",
                "Uploading to Gemini",
                commit=True
            )

            usage = frappe.get_doc({

                "doctype":
                "AI Usage Log",

                "call":
                docname,

                "status":
                "Failed",

                "error_message":
                str(e)

            })

            usage.insert(
                ignore_permissions=True
            )

            frappe.db.commit()

            frappe.log_error(
                frappe.get_traceback(),
                "Gemini Upload"
            )

            return "Failed"



        call_doc.db_set(

            "processing_status",

            "Waiting for Transcription",

            commit=True

        )

        call_doc.gemini_file_uri = (
            file_uri
        )

        call_doc.db_set(

            "processing_status",

            "Uploading to Gemini",

            commit=True

        )

        frappe.db.commit()


        active = wait_until_active(
            file_uri
        )

        if not active:

            call_doc.processing_status = (
                "Failed Transcription"
            )

            frappe.db.set_value("Call Intelligence", docname, "ai_error", _trunc("Gemini file never became ACTIVE", 1000))
            call_doc.db_set(
                "processing_status",
                "Uploading to Gemini",
                commit=True
            )

            frappe.db.commit()

            return "Failed"



        try:

            response = analyze_audio(
                file_uri
            )

        except Exception as e:

            call_doc.processing_status = (
                "Failed Transcription"
            )

            call_doc.retry_count = (
                call_doc.retry_count or 0
            ) + 1

            frappe.db.set_value("Call Intelligence", docname, "ai_error", _trunc(str(e), 1000))
            call_doc.db_set(
                "processing_status",
                "Uploading to Gemini",
                commit=True
            )

            frappe.db.commit()

            frappe.log_error(
                frappe.get_traceback(),
                "Gemini Analysis"
            )

            return "Failed"



        parsed = parse_gemini_response(
            response
        )


        save_ai_results(

            docname,

            parsed,

            response,

            file_uri

        )


        call_doc = frappe.get_doc(

            "Call Intelligence",

            docname

        )

        call_doc.processing_status = (

            "Success"

        )

        call_doc.db_set(

            "processing_status",

            "Uploading to Gemini",

            commit=True

        )

        frappe.db.commit()

        return "Success"


    except Exception as e:

        call_doc = frappe.get_doc(

            "Call Intelligence",

            docname

        )

        call_doc.processing_status = (

            "Failed Transcription"

        )

        call_doc.retry_count = (

            call_doc.retry_count or 0

        ) + 1

        call_doc.last_error = str(

            e

        )

        call_doc.db_set(

            "processing_status",

            "Uploading to Gemini",

            commit=True

        )

        frappe.db.commit()

        frappe.log_error(

            frappe.get_traceback(),

            "Gemini Processing"

        )

        return "Failed"   
    


def create_followup(doc):

    todo = frappe.get_doc({
        "doctype": "ToDo",
        "description": f"Follow up customer {doc.customer_name}",
        "reference_type": "Call Intelligence",
        "reference_name": doc.name,
        "status": "Open"
    })

    todo.insert(ignore_permissions=True)

    doc.followup_created = 1
    doc.followup_reference = todo.name
    doc.db_update()
    frappe.db.commit()

    frappe.db.commit()


def process_unprocessed_audio_files():

    files = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": ["in", ["", None]]
        },
        fields=["name", "file_name", "file_url"]
    )

    for f in files:

        # FIX 8: Guard against None file_name before calling .lower()
        if not f.file_name:
            continue

        if not f.file_name.lower().endswith((".m4a", ".mp3", ".wav", ".aac")):
            continue

        exists = frappe.db.exists(
            "Call Intelligence",
            {"recording_file": f.file_url}
        )

        if exists:
            continue

        doc = frappe.get_doc({
            "doctype": "Call Intelligence",
            "recording_file": f.file_url,
            "processing_status": "Pending"
        })

        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        frappe.enqueue(

            process_call_intelligence,

            queue="long",

            docname=doc.name

        )


def update_employee_kpi(doc):

    if not doc.employee_match:
        return

    kpi_name = frappe.db.exists(
        "Employee KPI",
        {"employee": doc.employee_match}
    )

    # FIX 5: Track whether this is a new record with an explicit flag instead
    # of relying on is_new() after insert (which always returns False post-insert).
    is_new_kpi = False

    if kpi_name:
        kpi = frappe.get_doc("Employee KPI", kpi_name)
    else:
        kpi = frappe.get_doc({
            "doctype": "Employee KPI",
            "employee": doc.employee_match
        })
        is_new_kpi = True

    kpi.calls_handled = (kpi.calls_handled or 0) + 1

    score = cint(doc.lead_score or 0)

    eval_score=cint(

    doc.overall_score or 0

    )
    avg=frappe.db.sql("""
    select avg(overall_score)
    from `tabEmployee Evaluation`
    where employee=%s
    """,
    doc.employee_match
    )[0][0]

    kpi.average_evaluation_score=avg or 0

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

    avg = frappe.db.sql(
        """
        SELECT AVG(lead_score)
        FROM `tabCall Intelligence`
        WHERE employee_match = %s
        """,
        doc.employee_match
    )[0][0]

    kpi.average_lead_score = avg or 0

    kpi.pending_followups = frappe.db.count(
        "ToDo",
        {
            "allocated_to": frappe.db.get_value(
                "Employee",
                doc.employee_match,
                "user_id"
            ),
            "status": "Open"
        }
    )

    kpi.last_updated = frappe.utils.now()
    if kpi.pending_followups > 25:
        frappe.log_error(
            kpi.employee,
            "Burnout Alert"
        )

    if is_new_kpi:
        kpi.insert(ignore_permissions=True)
    else:
        kpi.save(ignore_permissions=True)

    update_leaderboard()
    frappe.db.commit()


def update_customer_360(doc):

    if not doc.customer_360_match:
        return

    customer = frappe.get_doc("Customer", doc.customer_360_match)

    customer.communication_count = frappe.db.count(
        "Communication Event",
        {"customer": customer.name}
    )

    customer.last_contacted = frappe.utils.now()
    customer.last_summary = doc.summary
    customer.last_emotion = doc.emotion
    customer.last_visa_interest = doc.country_of_interest
    customer.current_counselor = doc.employee_match
    customer.last_sentiment = (
        doc.emotion
    )
    customer.last_lead_score = (
        doc.lead_score
    )

    customer.save(ignore_permissions=True)
    frappe.db.commit()

def log_ai_usage(doc):

    usage = frappe.get_doc(
        {
            "doctype":"AI Usage Log",
            "date":
            frappe.utils.today(),
            "employee":
            doc.employee_match,
            "call":
            doc.name
        }
    )

    usage.insert(
        ignore_permissions=True
    )
    frappe.db.commit()

def auto_create_call_intelligence(doc, method=None):

    if not doc.file_name:
        return

    if not doc.file_name.lower().endswith((".m4a", ".mp3", ".wav", ".aac")):
        return

    exists = frappe.db.exists(
        "Call Intelligence",
        {"recording_file": doc.file_url}
    )

    if exists:
        return

    ci = frappe.get_doc({
        "doctype": "Call Intelligence",
        "recording_file": doc.file_url,
        "processing_status": "Pending"
    })

    ci.insert(ignore_permissions=True)
    frappe.db.commit()

    process_call_intelligence(ci.name)


def retry_failed_calls():
    docs = frappe.get_all(
        "Call Intelligence",
        filters={
            "processing_status":[
                "in",
                [
                    "Failed to Upload to Gemini",
                    "Failed Transcription"
                ]
            ],
            "retry_count":[
                "<",
                3
            ]
        },

        fields=[
            "name"
        ]
    )

    for d in docs:
        frappe.enqueue(
            process_call_intelligence,
            queue="long",
            docname=d.name
        )    

def wait_until_active(file_uri):


    import requests


    api_key = get_api_key()


    file_name = file_uri.split("/")[-1]


    url = (

        "https://generativelanguage.googleapis.com"

        f"/v1beta/files/{file_name}"

        f"?key={api_key}"

    )


    for i in range(30):


        r = requests.get(url)


        data = r.json()


        state = (

            data

            .get(

                "state",

                ""

            )

        )


        if state=="ACTIVE":

            return True


        time.sleep(2)


    return False        


def unattended_leads():



    docs = frappe.get_all(

        "CRM Lead",

        filters={

            "status":"Open"

        },

        fields=[

            "name",

            "modified"

        ]

    )


    for d in docs:


        age = frappe.utils.time_diff_in_hours(

            frappe.utils.now(),

            d.modified

        )


        if age > 24:


            frappe.publish_realtime(

                "unattended_lead",

                {

                    "lead":d.name

                }

            )

@frappe.whitelist()

def retry_processing(name):


    doc=frappe.get_doc(

        "Call Intelligence",

        name

    )


    doc.retry_count=(

        doc.retry_count or 0

    )+1


    doc.db_update()
    frappe.db.commit()


    enqueue_processing(doc)


def send_followup_reminders():
    todos=frappe.get_all(
    "ToDo",
    filters={
    "status":"Open"
    }
    )
    for t in todos:
        pass
