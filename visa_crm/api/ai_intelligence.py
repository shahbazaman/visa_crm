import json
import frappe
from frappe.utils import cint, nowdate
from visa_crm.api.meta_utils import has_doctype, has_field, safe_json_dumps

AI_FIELDS=("summary","sentiment","lead_score","ai_next_best_action","ai_followup_suggestion","ai_lost_lead_analysis","ai_employee_coaching","ai_manager_summary","ai_reminder_suggestion","ai_customer_priority","ai_visa_recommendation","ai_quality_analysis","ai_timeline_summary")

def process_communication_ai(event_name):
    if not frappe.db.exists("Communication Event",event_name):
        return
    doc=frappe.get_doc("Communication Event",event_name)
    try:
        insights=analyze_event(doc)
        _update_event(doc,insights)
        _auto_task(doc,insights)
        _timeline(doc,insights)
        frappe.db.commit()
    except Exception:
        frappe.log_error(title="AI Intelligence Processing Failed",message=safe_json_dumps({"event":event_name,"traceback":frappe.get_traceback()}))

def analyze_event(doc):
    text="\n".join([str(getattr(doc,k,"") or "") for k in ("content","summary","source","direction")])
    prompt=f"""Analyze this Visa CRM communication and return JSON only with keys summary,sentiment,lead_score,next_best_action,followup_suggestion,lost_lead_analysis,employee_coaching,manager_summary,reminder_suggestion,customer_priority,visa_recommendation,auto_task,timeline_summary,quality_analysis. Communication: {text[:6000]}"""
    result=_gemini_json(prompt)
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

def _gemini_json(prompt):
    try:
        from visa_crm.api import gemini_service
        if hasattr(gemini_service,"generate_text"):
            raw=gemini_service.generate_text(prompt)
        elif hasattr(gemini_service,"analyze_text"):
            raw=gemini_service.analyze_text(prompt)
        else:
            return None
        return json.loads(raw.strip().strip("`").replace("json\n","",1))
    except Exception:
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

def _auto_task(doc,insights):
    if not insights.get("auto_task") or not has_doctype("ToDo"):
        return
    lead=getattr(doc,"lead",None)
    customer=getattr(doc,"customer",None)
    ref=lead or customer or doc.name
    ref_type="CRM Lead" if lead else ("Customer" if customer else "Communication Event")
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
    todo.insert(ignore_permissions=True)

def _timeline(doc,insights):
    if not has_doctype("Lead Timeline"):
        return
    message=insights.get("timeline_summary") or insights.get("summary")
    if not message:
        return
    tl=frappe.new_doc("Lead Timeline")
    if has_field("Lead Timeline","lead") and getattr(doc,"lead",None):
        tl.lead=doc.lead
    if has_field("Lead Timeline","customer") and getattr(doc,"customer",None):
        tl.customer=doc.customer
    for field in ("title","subject","description","note"):
        if has_field("Lead Timeline",field):
            tl.set(field,message)
    tl.insert(ignore_permissions=True)

def _staff():
    if frappe.session.user=="Guest" or not ({"System Manager","Sales Manager","Counselor","Visa Processing","Administrator"} & set(frappe.get_roles())):
        frappe.throw("Visa CRM staff access required", frappe.PermissionError)
