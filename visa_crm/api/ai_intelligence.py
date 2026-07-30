import json
import frappe
from frappe.utils import add_to_date,cint,now_datetime,nowdate
from visa_crm.api.meta_utils import has_doctype, has_field, safe_json_dumps

AI_FIELDS=("summary","sentiment","lead_score","ai_next_best_action","ai_followup_suggestion","ai_lost_lead_analysis","ai_employee_coaching","ai_manager_summary","ai_reminder_suggestion","ai_customer_priority","ai_visa_recommendation","ai_quality_analysis","ai_timeline_summary")

def process_communication_ai(event_name,queue_name=None,ai_job_name=None):
    if not frappe.db.exists("Communication Event",event_name):
        return
    if queue_name:
        return _process_staged_ai(event_name,queue_name,ai_job_name)
    doc=frappe.get_doc("Communication Event",event_name)
    try:
        insights=analyze_event(doc)
        _update_event(doc,insights)
        _auto_task(doc,insights)
        _timeline(doc,insights)
        frappe.db.commit()
    except Exception:
        frappe.log_error(title="AI Intelligence Processing Failed",message=safe_json_dumps({"event":event_name,"traceback":frappe.get_traceback()}))

def _process_staged_ai(event_name,queue_name,ai_job_name=None):
    from visa_crm.api.pipeline_engine import claim_stage,complete_stage,fail_stage,renew_stage_lease,skip_stage
    claim=claim_stage(queue_name,"AI_GEMINI",include_ai=True,lease_seconds=1800)
    if not claim:
        return
    active_claim=claim
    ai_job_name=ai_job_name or frappe.db.get_value("Lead Intake AI Job",{"queue":queue_name},"name")
    try:
        frappe.db.set_value("Lead Intake Queue",queue_name,{"ai_status":"Running","ai_error":"","ai_traceback":""},update_modified=False)
        if ai_job_name:
            frappe.db.set_value("Lead Intake AI Job",ai_job_name,{"state":"RUNNING","started_at":now_datetime(),"heartbeat_at":now_datetime(),"last_error_class":None,"last_error":None,"last_traceback":None},update_modified=False)
        frappe.db.commit()
        doc=frappe.get_doc("Communication Event",event_name)
        insights=analyze_event(doc,strict=True)
        renew_stage_lease(claim,lease_seconds=1800)
        _update_event(doc,insights)
        _auto_task(doc,insights,queue_name)
        _timeline(doc,insights,queue_name)
        complete_stage(claim,result={"communication_event":event_name,"insights":list(insights)})
        skip_stage(queue_name,"AI_TRANSLATION","No separate translation was required for the normalized AI response")
        summary_claim=claim_stage(queue_name,"AI_SUMMARY",include_ai=True)
        if summary_claim:
            active_claim=summary_claim
            complete_stage(summary_claim,result={"communication_event":event_name,"summary":insights.get("summary")},result_doctype="Communication Event",result_name=event_name)
            active_claim=None
        skip_stage(queue_name,"AI_EMBEDDING","No embedding provider is configured for this pipeline version")
        frappe.db.set_value("Lead Intake Queue",queue_name,{"ai_status":"Completed","ai_error":"","ai_traceback":""},update_modified=False)
        if ai_job_name:
            frappe.db.set_value("Lead Intake AI Job",ai_job_name,{"state":"COMPLETED","completed_at":now_datetime(),"heartbeat_at":now_datetime(),"next_retry_at":None,"result_json":safe_json_dumps(insights),"last_error_class":None,"last_error":None,"last_traceback":None},update_modified=False)
        frappe.db.commit()
    except Exception as exc:
        traceback=frappe.get_traceback()
        frappe.db.rollback()
        if active_claim:
            fail_stage(active_claim,exc,traceback=traceback)
        frappe.db.set_value("Lead Intake Queue",queue_name,{"ai_status":"Failed","ai_error":str(exc),"ai_traceback":traceback},update_modified=False)
        if ai_job_name:
            attempt=frappe.db.get_value("Lead Intake AI Job",ai_job_name,"attempt_count") or 1
            frappe.db.set_value("Lead Intake AI Job",ai_job_name,{"state":"FAILED","next_retry_at":add_to_date(now_datetime(),minutes=min(360,2**min(max(attempt,1),8))),"heartbeat_at":now_datetime(),"last_error_class":f"{type(exc).__module__}.{type(exc).__qualname__}","last_error":str(exc),"last_traceback":traceback},update_modified=False)
        frappe.db.commit()
        frappe.logger("visa_crm.ai").error(safe_json_dumps({"event":"staged_ai_failed","queue":queue_name,"communication_event":event_name,"exception_class":f"{type(exc).__module__}.{type(exc).__qualname__}","error":str(exc),"traceback":traceback}))

def analyze_event(doc,strict=False):
    text="\n".join([str(getattr(doc,k,"") or "") for k in ("content","summary","source","direction")])
    prompt=f"""Analyze this Visa CRM communication and return JSON only with keys summary,sentiment,lead_score,next_best_action,followup_suggestion,lost_lead_analysis,employee_coaching,manager_summary,reminder_suggestion,customer_priority,visa_recommendation,auto_task,timeline_summary,quality_analysis. Communication: {text[:6000]}"""
    result=_gemini_json(prompt,raise_errors=strict)
    if result:
        return result
    return _heuristic(text)

def manager_dashboard():
    if not has_doctype("Communication Event"):
        return {"performance":[],"sentiment":[],"recommendations":[],"date":nowdate()}
    fields=["count(name) as interactions"]
    group_by=None
    if has_field("Communication Event","employee"):
        fields.insert(0,"employee")
        group_by="employee"
    if has_field("Communication Event","lead_score"):
        fields.append("avg(lead_score) as avg_score")
    rows=frappe.get_all("Communication Event",fields=fields,group_by=group_by,limit_page_length=20)
    sentiment=frappe.get_all("Communication Event",fields=["sentiment","count(name) as count"],group_by="sentiment",limit_page_length=20) if has_field("Communication Event","sentiment") else []
    rec_fields=[f for f in ("name","ai_next_best_action","ai_customer_priority","customer","lead") if f=="name" or has_field("Communication Event",f)]
    filters={"ai_next_best_action":["is","set"]} if has_field("Communication Event","ai_next_best_action") else {}
    recommendations=frappe.get_all("Communication Event",fields=rec_fields,filters=filters,order_by="modified desc",limit_page_length=10) if has_field("Communication Event","ai_next_best_action") else []
    return {"performance":rows,"sentiment":sentiment,"recommendations":recommendations,"date":nowdate()}

def manager_daily_summary():
    data=manager_dashboard()
    actions=[r.get("ai_next_best_action") for r in data.get("recommendations",[]) if r.get("ai_next_best_action")]
    return {"date":data["date"],"summary":"; ".join(actions[:5]) or "No urgent AI recommendations today.","dashboard":data}

@frappe.whitelist()
def insights_dashboard():
    _staff()
    return manager_dashboard()

def _gemini_json(prompt,raise_errors=False):
    try:
        from visa_crm.api import gemini_service
        if hasattr(gemini_service,"generate_text"):
            raw=gemini_service.generate_text(prompt)
        elif hasattr(gemini_service,"analyze_text"):
            raw=gemini_service.analyze_text(prompt)
        else:
            if raise_errors:
                raise RuntimeError("Gemini text generation method is not configured")
            return None
        return json.loads(raw.strip().strip("`").replace("json\n","",1))
    except Exception:
        if raise_errors:
            raise
        return None

def _heuristic(text):
    low=(text or "").lower()
    score=70
    sentiment="Neutral"
    if any(x in low for x in ("urgent","ready","interested","approved","payment")):
        score=85
        sentiment="Positive"
    if any(x in low for x in ("not interested","cancel","reject","angry","refund","complaint")):
        score=35
        sentiment="Negative"
    return {"summary":(text[:220] or "No message content available."),"sentiment":sentiment,"lead_score":score,"next_best_action":"Follow up with the customer and confirm the next visa step.","followup_suggestion":"Schedule a follow-up within 24 hours.","lost_lead_analysis":"No lost lead signal detected." if score>=50 else "Customer may be at risk. Manager review recommended.","employee_coaching":"Keep response clear, timely, and document next action.","manager_summary":"Customer communication requires routine follow-up.","reminder_suggestion":"Create reminder for next business day.","customer_priority":score,"visa_recommendation":"Confirm destination, visa type, travel date, and document readiness.","auto_task":"Follow up on this communication.","timeline_summary":"AI reviewed communication and suggested next action.","quality_analysis":"Communication quality looks acceptable."}

def _update_event(doc,insights):
    values={"summary":insights.get("summary"),"sentiment":insights.get("sentiment"),"lead_score":cint(insights.get("lead_score")) or None,"ai_next_best_action":insights.get("next_best_action"),"ai_followup_suggestion":insights.get("followup_suggestion"),"ai_lost_lead_analysis":insights.get("lost_lead_analysis"),"ai_employee_coaching":insights.get("employee_coaching"),"ai_manager_summary":insights.get("manager_summary"),"ai_reminder_suggestion":insights.get("reminder_suggestion"),"ai_customer_priority":cint(insights.get("customer_priority")) or None,"ai_visa_recommendation":insights.get("visa_recommendation"),"ai_quality_analysis":insights.get("quality_analysis"),"ai_timeline_summary":insights.get("timeline_summary")}
    values={k:v for k,v in values.items() if v is not None and has_field("Communication Event",k)}
    if values:
        frappe.db.set_value("Communication Event",doc.name,values,update_modified=False)

def _auto_task(doc,insights,queue_name=None):
    if not insights.get("auto_task") or not has_doctype("ToDo"):
        return
    lead=getattr(doc,"lead",None)
    customer=getattr(doc,"customer",None)
    ref=lead or customer or doc.name
    ref_type="CRM Lead" if lead else ("Customer" if customer else "Communication Event")
    key=f"ai-task:{queue_name}" if queue_name else None
    if key and has_field("ToDo","meta_intake_key") and frappe.db.exists("ToDo",{"meta_intake_key":key}):
        return
    if frappe.db.exists("ToDo",{"reference_type":ref_type,"reference_name":ref,"description":insights.get("auto_task")}):
        return
    todo=frappe.new_doc("ToDo")
    todo.description=insights.get("auto_task")
    todo.reference_type=ref_type
    todo.reference_name=ref
    todo.status="Open"
    assigned=getattr(doc,"assigned_user",None)
    if assigned:
        todo.allocated_to=assigned
    if key and has_field("ToDo","meta_intake_key"):
        todo.meta_intake_key=key
    todo.insert(ignore_permissions=True)

def _timeline(doc,insights,queue_name=None):
    if not has_doctype("Lead Timeline"):
        return
    message=insights.get("timeline_summary") or insights.get("summary")
    if not message:
        return
    key=f"ai-timeline:{queue_name}" if queue_name else None
    if key and has_field("Lead Timeline","meta_intake_key") and frappe.db.exists("Lead Timeline",{"meta_intake_key":key}):
        return
    tl=frappe.new_doc("Lead Timeline")
    if has_field("Lead Timeline","lead") and getattr(doc,"lead",None):
        tl.lead=doc.lead
    if has_field("Lead Timeline","customer") and getattr(doc,"customer",None):
        tl.customer=doc.customer
    for field in ("title","subject","description","note"):
        if has_field("Lead Timeline",field):
            tl.set(field,message)
    if key and has_field("Lead Timeline","meta_intake_key"):
        tl.meta_intake_key=key
    tl.insert(ignore_permissions=True)

def _staff():
    if frappe.session.user=="Guest" or not ({"System Manager","Sales Manager","Counselor","Visa Processing","Administrator"} & set(frappe.get_roles())):
        frappe.throw("Visa CRM staff access required", frappe.PermissionError)
