import frappe
from frappe.utils import add_to_date, get_datetime, now, now_datetime
from visa_crm.api.customer360 import link_or_create_lead
from visa_crm.api.followup import create_meta_followup
from visa_crm.api.lead_assignment import assign_lead
from visa_crm.api.meta_graph import MetaGraphError, fetch_lead
from visa_crm.api.meta_mapping import normalize_lead
from visa_crm.api.meta_utils import MAX_RETRIES, get_meta_settings, has_field, load_json, log_exception, log_info, meta_debug_log, queue_status, retry_count, safe_json_dumps, set_values
from visa_crm.api.workflow import create_deal_if_supported, mark_lead_stage, qualify_lead

def process_pending(limit=100):
    meta_debug_log("process_pending_start", status="scheduler", limit=limit)
    rows = _pending_rows(limit)
    for row in rows:
        process_queue(row.name)
    meta_debug_log("process_pending_end", status="scheduler", count=len(rows), limit=limit)

def process_queue(docname):
    initial_status = frappe.db.get_value("Lead Intake Queue", docname, "status")
    initial_source = frappe.db.get_value("Lead Intake Queue", docname, "source_lead_id")
    meta_debug_log("process_queue_start", queue_name=docname, source_lead_id=initial_source, status=initial_status)
    if not _claim(docname):
        meta_debug_log("process_queue_end", queue_name=docname, source_lead_id=initial_source, status=initial_status, skipped="claim_failed")
        return
    doc = frappe.get_doc("Lead Intake Queue", docname)
    try:
        settings = get_meta_settings()
        leadgen_id = doc.source_lead_id or _leadgen_id(doc)
        context = _context(doc, leadgen_id)
        if not leadgen_id:
            raise ValueError("Lead Intake Queue is missing source_lead_id")
        graph_payload = fetch_lead(leadgen_id, settings, context)
        data = normalize_lead(graph_payload, settings, context)
        _update_queue(doc, data, graph_payload, "Lead Downloaded")
        context = _context(doc, data.get("source_lead_id") or leadgen_id)
        matches = link_or_create_lead(data, context)
        _link_matches(doc, matches)
        context = _context(doc, data.get("source_lead_id") or leadgen_id)
        lead = matches.get("lead")
        customer = matches.get("customer")
        if lead:
            mark_lead_stage(lead, "Lead", context)
            qualify_lead(lead, context)
            create_deal_if_supported(lead, data)
        employee = assign_lead(lead, doc, context=context)
        event = _communication_event(data, lead, customer, employee, doc.name, context)
        todo = create_meta_followup(data, lead, customer, employee, doc.name, context)
        _finish(doc, lead, customer, employee, event, todo)
        frappe.db.commit()
        log_info("meta_queue_completed", queue=doc.name, lead=lead, customer=customer, employee=employee)
        meta_debug_log("process_queue_end", queue_name=doc.name, source_lead_id=data.get("source_lead_id") or leadgen_id, status="Processed", lead=lead, customer=customer, employee=employee)
    except MetaGraphError as exc:
        meta_debug_log("process_queue_exception", queue_name=docname, source_lead_id=frappe.db.get_value("Lead Intake Queue", docname, "source_lead_id"), status=frappe.db.get_value("Lead Intake Queue", docname, "status"), error=str(exc), graph_response=getattr(exc, "response", None), graph_request=getattr(exc, "request", None))
        frappe.db.rollback()
        _retry_or_fail(docname, str(exc), retryable=True, graph_response=getattr(exc, "response", None), graph_request=getattr(exc, "request", None))
    except Exception as exc:
        meta_debug_log("process_queue_exception", queue_name=docname, source_lead_id=frappe.db.get_value("Lead Intake Queue", docname, "source_lead_id"), status=frappe.db.get_value("Lead Intake Queue", docname, "status"), error=str(exc), traceback=frappe.get_traceback())
        frappe.db.rollback()
        log_exception("meta_queue_failed", queue=docname, error=str(exc))
        _retry_or_fail(docname, str(exc), retryable=False)

def _pending_rows(limit):
    filters = {"status": ["in", ["Lead Received", "Failed"]]}
    rows = frappe.get_all("Lead Intake Queue", filters=filters, fields=["name", "status"], order_by="creation asc", limit=int(limit or 100))
    if not has_field("Lead Intake Queue", "next_retry_at"):
        return [row for row in rows if row.status == "Lead Received"]
    pending = []
    for row in rows:
        if row.status == "Lead Received":
            pending.append(row)
            continue
        next_retry = frappe.db.get_value("Lead Intake Queue", row.name, "next_retry_at")
        count = frappe.db.get_value("Lead Intake Queue", row.name, "retry_count") if has_field("Lead Intake Queue", "retry_count") else MAX_RETRIES
        if next_retry and get_datetime(next_retry) <= now_datetime() and (count or 0) < MAX_RETRIES:
            pending.append(row)
    return pending

def _claim(docname):
    source_lead_id = frappe.db.get_value("Lead Intake Queue", docname, "source_lead_id")
    meta_debug_log("queue_status_update_start", queue_name=docname, source_lead_id=source_lead_id, status="Fetching Meta Lead")
    if has_field("Lead Intake Queue", "processing_started_at"):
        frappe.db.sql("""update `tabLead Intake Queue` set status=%s,processing_started_at=%s where name=%s and status in (%s,%s)""", ("Fetching Meta Lead", now(), docname, "Lead Received", "Failed"))
    else:
        frappe.db.sql("""update `tabLead Intake Queue` set status=%s where name=%s and status in (%s,%s)""", ("Fetching Meta Lead", docname, "Lead Received", "Failed"))
    frappe.db.commit()
    claimed = frappe.db.get_value("Lead Intake Queue", docname, "status") == "Fetching Meta Lead"
    meta_debug_log("queue_status_update_end", queue_name=docname, source_lead_id=source_lead_id, status=frappe.db.get_value("Lead Intake Queue", docname, "status"), claimed=claimed)
    return claimed

def _leadgen_id(doc):
    payload = load_json(doc.raw_payload, {})
    return str((payload.get("value") or {}).get("leadgen_id") or "")

def _update_queue(doc, data, graph_payload, status):
    meta_debug_log("queue_status_update_start", queue_name=doc.name, source_lead_id=data.get("source_lead_id") or doc.source_lead_id, status=status)
    values = {field: data.get(field) for field in ("source_lead_id", "customer_name", "phone", "email", "country_interested", "visa_type", "campaign_name", "adset_name", "ad_name")}
    values.update({"status": status, "graph_payload": safe_json_dumps(graph_payload), "custom_answers": safe_json_dumps(data.get("custom_answers")), "page_id": data.get("page_id"), "form_id": data.get("form_id"), "campaign_id": data.get("campaign_id"), "ad_id": data.get("ad_id")})
    set_values("Lead Intake Queue", doc.name, values)
    doc.reload()
    meta_debug_log("queue_status_update_end", queue_name=doc.name, source_lead_id=doc.source_lead_id, status=doc.status)

def _link_matches(doc, matches):
    status = "Customer Matched" if matches.get("customer") else "Lead Created"
    meta_debug_log("queue_status_update_start", queue_name=doc.name, source_lead_id=doc.source_lead_id, status=status)
    set_values("Lead Intake Queue", doc.name, {"matched_customer": matches.get("customer"), "matched_lead": matches.get("lead"), "status": status})
    doc.reload()
    meta_debug_log("queue_status_update_end", queue_name=doc.name, source_lead_id=doc.source_lead_id, status=doc.status)

def _finish(doc, lead, customer, employee, event, todo):
    meta_debug_log("queue_status_update_start", queue_name=doc.name, source_lead_id=doc.source_lead_id, status="Processed")
    set_values("Lead Intake Queue", doc.name, {"matched_customer": customer, "matched_lead": lead, "assigned_employee": employee, "communication_event": event, "followup_reference": todo, "processing_completed_at": now(), "next_retry_at": None, "status": "Processed", "last_error": ""})
    meta_debug_log("queue_status_update_end", queue_name=doc.name, source_lead_id=doc.source_lead_id, status="Processed")

def _communication_event(data, lead, customer, employee, queue_name, context=None):
    context = context or {}
    meta_debug_log("communication_event_creation_start", lead=lead, customer=customer, employee=employee, **context)
    if frappe.db.exists("Communication Event", {"event_id": f"meta:{data.get('source_lead_id')}"}):
        existing = frappe.db.get_value("Communication Event", {"event_id": f"meta:{data.get('source_lead_id')}"}, "name")
        meta_debug_log("communication_event_creation_end", communication_event=existing, existing=True, **context)
        return existing
    doc = frappe.new_doc("Communication Event")
    values = {"event_id": f"meta:{data.get('source_lead_id')}", "source": "Meta Form", "event_type": "Lead", "direction": "Inbound", "customer": customer, "lead": lead, "employee": employee, "phone": data.get("phone"), "email": data.get("email"), "content": safe_json_dumps(data.get("custom_answers")), "summary": f"Meta Lead Ads intake for {data.get('customer_name') or data.get('phone') or data.get('email')}", "event_datetime": now(), "channel_id": queue_name}
    for field, value in values.items():
        if doc.meta.has_field(field):
            doc.set(field, value)
    doc.insert(ignore_permissions=True)
    meta_debug_log("communication_event_creation_end", communication_event=doc.name, existing=False, **context)
    return doc.name

def _retry_or_fail(docname, error, retryable, graph_response=None, graph_request=None):
    doc = frappe.get_doc("Lead Intake Queue", docname)
    count = retry_count(doc) + 1
    status = "Failed"
    values = {"retry_count": count, "last_error": error[:1000], "next_retry_at": None, "processing_completed_at": now()}
    if graph_response is not None:
        values["graph_payload"] = safe_json_dumps(graph_response)
        values["graph_api_response"] = safe_json_dumps(graph_response)
    if graph_request is not None:
        values["graph_api_request"] = safe_json_dumps(graph_request)
    if retryable and count < MAX_RETRIES:
        values["next_retry_at"] = add_to_date(now(), minutes=min(60, 2 ** count))
    queue_status(docname, status, **values)
    frappe.db.commit()
    log_info("meta_queue_retry_state", queue=docname, status=status, retry_count=count, error=error[:200])

def _context(doc, source_lead_id=None):
    return {"queue_name": doc.name, "source_lead_id": source_lead_id or doc.source_lead_id, "status": doc.status}
