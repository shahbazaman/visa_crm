import frappe
from frappe.utils import now
from visa_crm.api.customer360 import link_or_create_lead
from visa_crm.api.followup import create_meta_followup
from visa_crm.api.lead_assignment import assign_lead
from visa_crm.api.workflow import mark_lead_stage

@frappe.whitelist()
def create_manual_lead(data=None, **kwargs):
    _staff()
    data = frappe._dict(data or kwargs)
    payload = _normalize(data)
    matches = link_or_create_lead(payload, _context(payload))
    lead = matches.get("lead")
    customer = matches.get("customer")
    employee = assign_lead(lead, context=_context(payload))
    if lead:
        mark_lead_stage(lead, "New", _context(payload))
    todo = create_meta_followup(payload, lead, customer, employee, None, _context(payload))
    _queue(payload, lead, customer, employee, todo)
    frappe.db.commit()
    return {"lead": lead, "customer": customer, "employee": employee, "todo": todo}

def _normalize(data):
    return {"customer_name": data.get("customer_name") or data.get("name"), "phone": data.get("phone") or data.get("mobile_no"), "whatsapp": data.get("whatsapp") or data.get("whatsapp_number"), "email": data.get("email"), "visa_type": data.get("visa_type"), "country_interested": data.get("country_interested") or data.get("country"), "campaign_name": data.get("campaign_name"), "ad_name": data.get("ad_name"), "source": data.get("source") or "Manual", "source_lead_id": data.get("source_lead_id") or f"manual-{frappe.generate_hash(length=10)}"}

def _queue(data, lead, customer, employee, todo):
    if not frappe.db.exists("DocType", "Lead Intake Queue"):
        return None
    existing = frappe.db.exists("Lead Intake Queue", {"source_lead_id": data.get("source_lead_id")})
    if existing:
        return existing
    doc = frappe.new_doc("Lead Intake Queue")
    for field, value in {"status": "Processed", "lead_source": data.get("source"), "source_lead_id": data.get("source_lead_id"), "customer_name": data.get("customer_name"), "phone": data.get("phone"), "email": data.get("email"), "country_interested": data.get("country_interested"), "visa_type": data.get("visa_type"), "matched_customer": customer, "matched_lead": lead, "assigned_employee": employee, "followup_reference": todo, "raw_payload": frappe.as_json(data), "processing_completed_at": now()}.items():
        if doc.meta.has_field(field):
            doc.set(field, value)
    doc.insert(ignore_permissions=True)
    return doc.name

def _context(data):
    return {"queue_name": None, "source_lead_id": data.get("source_lead_id"), "status": "Manual"}

def _staff():
    if frappe.session.user=="Guest" or not ({"System Manager","Sales Manager","Counselor","Visa Processing","Administrator"} & set(frappe.get_roles())):
        frappe.throw("Visa CRM staff access required", frappe.PermissionError)
