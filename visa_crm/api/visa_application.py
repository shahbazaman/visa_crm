import frappe
from visa_crm.api.meta_utils import has_doctype, set_if_has

def create_for_lead(lead, customer=None, data=None, queue_name=None):
    if not has_doctype("Visa Application"):
        frappe.throw("Visa Application DocType is not installed")
    data = data or {}
    key=f"visa:{queue_name}" if queue_name else None
    existing=frappe.db.exists("Visa Application",{"meta_intake_key":key}) if key and frappe.get_meta("Visa Application").has_field("meta_intake_key") else None
    if not key:
        existing=existing or frappe.db.exists("Visa Application",{"lead":lead})
    if existing and not customer and not data:
        return existing
    lead_doc = frappe.get_doc("CRM Lead", lead)
    customer = customer or getattr(lead_doc, "customer360", None) or getattr(lead_doc, "customer_360", None) or getattr(lead_doc, "customer_360_match", None)
    answers=data.get("custom_answers") or data.get("meta_fields") or {}
    values={"lead":lead,"customer":customer,"applicant_name":data.get("customer_name") or getattr(lead_doc,"lead_name",None) or getattr(lead_doc,"first_name",None),"visa_type":data.get("visa_type") or getattr(lead_doc,"visa_type",None),"country":data.get("country_interested") or getattr(lead_doc,"country_interested",None),"destination":data.get("destination") or data.get("country_interested"),"travel_month":data.get("travel_month"),"budget":data.get("budget"),"passport_status":data.get("passport") or data.get("passport_status"),"notes":data.get("notes") or data.get("message"),"campaign_source":data.get("campaign_name") or data.get("lead_source"),"meta_campaign_id":data.get("campaign_id"),"meta_campaign_name":data.get("campaign_name"),"meta_answers_json":frappe.as_json(answers) if answers else None,"status":"Draft","meta_intake_key":key}
    if existing:
        doc = frappe.get_doc("Visa Application", existing)
        changed = False
        for field, value in values.items():
            if value is not None and doc.meta.has_field(field) and not doc.get(field):
                doc.set(field, value)
                changed = True
        if changed:
            doc.save(ignore_permissions=True)
    else:
        doc = frappe.new_doc("Visa Application")
        for field, value in values.items():
            set_if_has(doc, field, value)
        doc.insert(ignore_permissions=True)
    if lead_doc.meta.has_field("visa_application") and not lead_doc.get("visa_application"):
        frappe.db.set_value("CRM Lead", lead, "visa_application", doc.name, update_modified=False)
    if customer and has_doctype("Customer") and frappe.get_meta("Customer").has_field("visa_application") and not frappe.db.get_value("Customer", customer, "visa_application"):
        frappe.db.set_value("Customer", customer, "visa_application", doc.name, update_modified=False)
    return doc.name
