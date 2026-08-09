import frappe
from visa_crm.api.meta_utils import has_field

# Default Customer Group for Meta-generated customers.
# Must be a non-group Customer Group (is_group=0).
# "Individual" is the standard Frappe default leaf group.
_DEFAULT_CUSTOMER_GROUP = "Individual"


def _resolve_customer_group():
    """Return a valid (non-group) Customer Group name for new Customer creation.

    Falls back through a priority list so the system works even if the
    Frappe installation has renamed standard groups.
    """
    preferred = ("Individual", "Commercial", "Non Profit", "Government")
    for group in preferred:
        row = frappe.db.get_value(
            "Customer Group",
            {"name": group, "is_group": 0},
            "name",
        )
        if row:
            return row
    # Last resort: pick any non-group Customer Group that exists
    any_group = frappe.db.get_value(
        "Customer Group",
        {"is_group": 0},
        "name",
        order_by="name asc",
    )
    if any_group:
        return any_group
    # If no non-group Customer Group exists at all, raise early with a clear message
    raise frappe.ValidationError(
        "No non-group Customer Group found. "
        "Please create at least one leaf Customer Group (e.g. 'Individual')."
    )


def find_customer(phone=None, email=None, name=None):
    if phone:
        for field in ("mobile_no", "whatsapp_no"):
            if has_field("Customer", field):
                customer = frappe.db.get_value("Customer", {field: phone}, "name")
                if customer:
                    return customer
    if email:
        if has_field("Customer", "email_id"):
            customer = frappe.db.get_value("Customer", {"email_id": email}, "name")
            if customer:
                return customer
    return None


def find_lead(phone=None, email=None):
    if phone:
        lead = frappe.db.get_value("CRM Lead", {"mobile_no": phone}, "name")
        if lead:
            return lead
    if email:
        lead = frappe.db.get_value("CRM Lead", {"email": email}, "name")
        if lead:
            return lead
    return None


def create_customer_from_lead(lead, data=None):
    data = data or {}
    doc = frappe.get_doc("CRM Lead", lead)
    values = dict(data)
    values["customer_name"] = (
        data.get("customer_name") or doc.lead_name or doc.first_name
    )
    values["phone"] = data.get("phone") or getattr(doc, "mobile_no", None)
    values["email"] = data.get("email") or getattr(doc, "email", None)
    return create_customer(values)


def create_customer(data):
    data = data or {}
    name = data.get("customer_name") or (
        f"Meta Lead {data.get('source_lead_id') or ''}".strip()
    )
    phone = data.get("phone")
    email = data.get("email")
    existing = find_customer(phone, email)
    if existing:
        return existing
    customer = frappe.new_doc("Customer")
    # Resolve a valid non-group Customer Group to avoid the
    # "Cannot select a Group type Customer Group" ValidationError
    # that occurs when customer_group defaults to "All Customer Groups".
    customer_group = _resolve_customer_group()
    values = {
        "customer_name": name,
        "customer_type": "Individual",
        "customer_group": customer_group,
        "mobile_no": phone,
        "whatsapp_no": data.get("whatsapp") or phone,
        "email_id": email,
    }
    for field, value in values.items():
        if value is not None and customer.meta.has_field(field):
            customer.set(field, value)
    try:
        customer.insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        existing = find_customer(phone, email)
        if existing:
            return existing
        raise
    return customer.name
