import frappe
from visa_crm.api.customer import create_customer_from_lead
from visa_crm.api.lead_creator import create_crm_lead
from visa_crm.api.meta_utils import has_doctype, has_field, meta_debug_log, normalize_phone

PHONE_FIELDS = ("mobile_no", "phone", "phone_number", "whatsapp_no", "whatsapp_number")
EMAIL_FIELDS = ("email_id", "email")

def match_lead_data(data, context=None):
    context = context or {}
    meta_debug_log("customer_360_matching_start", **context)
    phones = [normalize_phone(data.get("phone")), normalize_phone(data.get("whatsapp"))]
    emails = [(data.get("email") or "").strip().lower()]
    customer = _match("Customer", phones, emails, data.get("customer_name"))
    lead = _match("CRM Lead", phones, emails, data.get("customer_name"), data.get("source_lead_id"))
    meta_debug_log("customer_360_matching_end", matched_customer=customer, matched_lead=lead, **context)
    return {"customer": customer, "lead": lead}

def link_or_create_lead(data, context=None):
    context = context or {}
    matches = match_lead_data(data, context)
    if not matches["lead"]:
        matches["lead"] = create_crm_lead(data, context)
    if not matches["customer"]:
        matches["customer"] = create_customer_from_lead(matches["lead"], data)
    _link_lead_customer(matches["lead"], matches["customer"])
    return matches

def update_customer_profile(doc):
    if not doc.customer_360_match:
        return
    customer = frappe.get_doc("Customer", doc.customer_360_match)
    customer.last_contacted = frappe.utils.now()
    customer.last_summary = doc.summary
    customer.last_sentiment = doc.emotion
    customer.last_lead_score = doc.lead_score
    customer.current_counselor = doc.employee_match
    customer.last_visa_interest = doc.country_of_interest
    customer.communication_count = frappe.db.count("Communication Event", {"customer": customer.name})
    customer.save(ignore_permissions=True)
    frappe.db.commit()

def link_customer(call_doc):
    if call_doc.customer_360_match:
        return
    customer = _match("Customer", [call_doc.customer_phone_extracted], [], call_doc.customer_name)
    if customer:
        call_doc.db_set("customer_360_match", customer, update_modified=False)
        if call_doc.communication_event:
            event = frappe.get_doc("Communication Event", call_doc.communication_event)
            event.customer = customer
            event.save(ignore_permissions=True)
        frappe.db.commit()

def _match(doctype, phones, emails, name=None, source_lead_id=None):
    if not has_doctype(doctype):
        return None
    if doctype == "CRM Lead" and source_lead_id and has_field(doctype, "facebook_lead_id"):
        return frappe.db.get_value(doctype, {"facebook_lead_id": source_lead_id}, "name")
    for phone in filter(None, phones):
        for field in PHONE_FIELDS:
            if has_field(doctype, field):
                found = frappe.db.get_value(doctype, {field: phone}, "name")
                if found:
                    return found
    for email in filter(None, emails):
        for field in EMAIL_FIELDS:
            if has_field(doctype, field):
                found = frappe.db.get_value(doctype, {field: email}, "name")
                if found:
                    return found
    if name and has_field(doctype, "customer_name"):
        return frappe.db.get_value(doctype, {"customer_name": name}, "name")
    return None

def _link_lead_customer(lead, customer):
    lead_values = {}
    for field in ("customer360", "customer_360", "customer_360_match"):
        if not has_field("CRM Lead", field):
            continue
        current = frappe.db.get_value("CRM Lead", lead, field)
        if current and current != customer:
            frappe.throw(f"CRM Lead {lead} is already linked to Customer {current}")
        if not current:
            lead_values[field] = customer
    if lead_values:
        frappe.db.set_value("CRM Lead", lead, lead_values, update_modified=False)
    if has_field("Customer", "crm_lead") and not frappe.db.get_value("Customer", customer, "crm_lead"):
        frappe.db.set_value("Customer", customer, "crm_lead", lead, update_modified=False)
