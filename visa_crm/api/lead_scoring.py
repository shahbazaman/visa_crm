import frappe

def update_lead_score(call_doc):
    if not call_doc.lead_match:
        return
    lead=frappe.get_doc("CRM Lead",call_doc.lead_match)
    old_score=float(lead.custom_ai_lead_score or 0)
    new_score=float(call_doc.lead_score or 0)
    lead.custom_ai_lead_score=new_score
    lead.save(ignore_permissions=True)
    frappe.get_doc({
        "doctype":"Lead Score History",
        "lead":lead.name,
        "old_score":old_score,
        "new_score":new_score,
        "score_change":new_score-old_score,
        "employee":call_doc.employee_match,
        "customer":call_doc.customer_360_match,
        "call_intelligence":call_doc.name,
        "score":new_score,
        "intent":call_doc.lead_intent,
        "emotion":call_doc.emotion,
        "recorded_on":frappe.utils.now_datetime()
    }).insert(ignore_permissions=True)
    history=frappe.get_all(
        "Lead Score History",
        filters={"lead":call_doc.lead_match},
        fields=["score"]
    )
    if history:
        avg=sum(float(d.score) for d in history)/len(history)
        lead=frappe.get_doc("CRM Lead",call_doc.lead_match)
        if hasattr(lead,"lead_score"):
            lead.lead_score=avg
        if hasattr(lead,"custom_average_ai_score"):
            lead.custom_average_ai_score=avg
        lead.save(ignore_permissions=True)
    frappe.db.commit()