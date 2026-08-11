import hashlib
import frappe
from visa_crm.api.customer import create_customer,create_customer_from_lead
from visa_crm.api.lead_creator import create_crm_lead
from visa_crm.api.meta_utils import has_doctype, has_field, meta_debug_log, normalize_phone

PHONE_FIELDS = ("mobile_no", "phone", "phone_number", "whatsapp_no", "whatsapp_number")
EMAIL_FIELDS = ("email_id", "email")

def match_lead_data(data, context=None):
    context = context or {}
    meta_debug_log("customer_360_matching_start", **context)
    phones = [normalize_phone(data.get("phone")), normalize_phone(data.get("whatsapp"))]
    emails = [(data.get("email") or "").strip().lower()]
    customer = _identity_customer(data) or _match("Customer", phones, emails)
    lead = _match("CRM Lead", phones, emails, source_lead_id=data.get("source_lead_id"))
    meta_debug_log("customer_360_matching_end", matched_customer=customer, matched_lead=lead, **context)
    return {"customer": customer, "lead": lead}

def link_or_create_lead(data, context=None):
    context = context or {}
    matches=match_lead_data(data,context)
    if not matches["lead"]:
        matches["lead"]=create_crm_lead(data,context)
    if not matches["customer"]:
        matches["customer"]=create_customer_from_lead(matches["lead"],data)
    _link_lead_customer(matches["lead"],matches["customer"])
    return matches

def resolve_customer(data,context=None):
    context=context or {}
    customer=_identity_customer(data)
    lead=_match("CRM Lead",[],[],source_lead_id=data.get("source_lead_id"))
    if not customer and lead:
        customer=_linked_customer(lead)
    if not customer:
        phones=[normalize_phone(data.get("phone")),normalize_phone(data.get("whatsapp"))]
        emails=[(data.get("email") or "").strip().lower()]
        customer=_match("Customer",phones,emails)
    if not customer:
        customer=create_customer(data)
    _populate_customer_blanks(customer,data)
    _claim_identities(customer,data)
    meta_debug_log("customer_360_customer_resolved",customer=customer,**context)
    return customer

def _populate_customer_blanks(customer,data):
    if not customer or not frappe.db.exists("Customer",customer):
        return
    current=frappe.db.get_value("Customer",customer,["customer_name","mobile_no","email_id","whatsapp_no"],as_dict=True) or {}
    values={}
    if data.get("customer_name") and (not current.get("customer_name") or current.get("customer_name").startswith("Meta Lead ")):
        values["customer_name"]=data.get("customer_name")
    if data.get("phone") and not current.get("mobile_no"):
        values["mobile_no"]=data.get("phone")
    if data.get("whatsapp") and not current.get("whatsapp_no"):
        values["whatsapp_no"]=data.get("whatsapp")
    if data.get("email") and not current.get("email_id"):
        values["email_id"]=data.get("email")
    values={f:v for f,v in values.items() if has_field("Customer",f)}
    if values:
        frappe.db.set_value("Customer",customer,values,update_modified=False)

def resolve_lead(data,customer,context=None):
    context=context or {}
    phones=[normalize_phone(data.get("phone")),normalize_phone(data.get("whatsapp"))]
    emails=[(data.get("email") or "").strip().lower()]
    lead=_match("CRM Lead",phones,emails,source_lead_id=data.get("source_lead_id"))
    if not lead:
        try:
            lead=create_crm_lead(data,context)
        except frappe.DuplicateEntryError:
            lead=_match("CRM Lead",phones,emails,source_lead_id=data.get("source_lead_id"))
            if not lead:
                raise
    _populate_lead_blanks(lead,data)
    _link_lead_customer(lead,customer)
    meta_debug_log("customer_360_lead_resolved",lead=lead,customer=customer,**context)
    return lead

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
    customer = _match("Customer", [call_doc.customer_phone_extracted], [])
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

def _identity_customer(data):
    if not has_doctype("Customer Identity"):
        return None
    for identity_type,value in _identities(data):
        customer=frappe.db.get_value("Customer Identity",_identity_hash(identity_type,value),"customer")
        if customer and frappe.db.exists("Customer",customer):
            return customer
    return None

def _claim_identities(customer, data):
    if not has_doctype("Customer Identity"):
        return
    for identity_type, value in _identities(data):
        digest = _identity_hash(identity_type, value)
        existing = frappe.db.get_value("Customer Identity", digest, "customer")
        if existing:
            if existing != customer:
                meta_debug_log("customer_identity_conflict", customer=customer, existing_customer=existing, identity_type=identity_type)
            continue
        doc = frappe.new_doc("Customer Identity")
        doc.update({
            "identity_hash": digest,
            "identity_type": identity_type,
            "masked_value": _mask(value),
            "customer": customer,
            "verified": 0,
            "source": "Meta Lead Ads"
        })
        try:
            doc.insert(ignore_permissions=True)
        except frappe.DuplicateEntryError:
            pass
        except Exception as exc:
            meta_debug_log("customer_identity_insert_error", error=str(exc), identity_type=identity_type)

def _identities(data):
    values=[("External ID",str(data.get("source_lead_id") or "").strip()),("Phone",normalize_phone(data.get("phone"))),("WhatsApp",normalize_phone(data.get("whatsapp"))),("Email",(data.get("email") or "").strip().lower())]
    return [(kind,value) for kind,value in values if value]

def _identity_hash(identity_type,value):
    return hashlib.sha256(f"{identity_type}:{value}".encode("utf-8")).hexdigest()

def _mask(value):
    value=str(value)
    return value if len(value)<=4 else f"{value[:2]}{'*'*(len(value)-4)}{value[-2:]}"

def _linked_customer(lead):
    for field in ("customer360","customer_360","customer_360_match"):
        if has_field("CRM Lead",field):
            customer=frappe.db.get_value("CRM Lead",lead,field)
            if customer and frappe.db.exists("Customer",customer):
                return customer
    return None

def _populate_lead_blanks(lead,data):
    mapping={"facebook_lead_id":"source_lead_id","facebook_form_id":"form_id","facebook_page_id":"page_id","meta_campaign_id":"campaign_id","meta_campaign_name":"campaign_name","meta_adset_id":"adset_id","meta_adset_name":"adset_name","meta_ad_id":"ad_id","meta_ad_name":"ad_name","mobile_no":"phone","email":"email"}
    current=frappe.db.get_value("CRM Lead",lead,list(mapping)+["lead_name"],as_dict=True) or {}
    values={target:data.get(source) for target,source in mapping.items() if data.get(source) and not current.get(target)}
    if data.get("customer_name") and (not current.get("lead_name") or current.get("lead_name").startswith("Meta Lead ")):
        values["lead_name"]=data.get("customer_name")
    values={f:v for f,v in values.items() if has_field("CRM Lead",f)}
    if values:
        frappe.db.set_value("CRM Lead",lead,values,update_modified=False)
