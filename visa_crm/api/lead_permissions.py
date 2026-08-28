import frappe
from frappe.utils import cint


DEFAULT_MANAGEMENT_ROLES = {
    "System Manager",
    "Administrator",
    "Sales Manager",
    "General Manager",
    "Managing Director",
    "MD",
    "CRM Manager",
    "HR Manager",
    "HR User",
    "HR",
}
DEFAULT_OPERATIONAL_ROLES = {"Sales User", "Counselor", "Visa Processing", "Lead Team", "Inbox User"}


def management_roles():
    try:
        conf = getattr(frappe, "conf", None)
        configured = (conf.get("visa_crm_management_roles") if conf else None) or []
    except Exception:
        configured = []
    if isinstance(configured, str):
        configured = [role.strip() for role in configured.split(",") if role.strip()]
    return DEFAULT_MANAGEMENT_ROLES | set(configured or [])


def is_management(user=None):
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    roles = set(frappe.get_roles(user))
    return bool(management_roles() & roles)


def require_management():
    if not is_management():
        frappe.throw("Management access required", frappe.PermissionError)


def is_operational(user=None):
    user = user or frappe.session.user
    roles = set(frappe.get_roles(user))
    return is_management(user) or bool(DEFAULT_OPERATIONAL_ROLES & roles)


def accessible_categories(user=None):
    user = user or frappe.session.user
    if is_management(user):
        return frappe.get_all("Lead Category", filters={"is_active": 1}, pluck="name")
    if not is_operational(user):
        return []
    categories = set(frappe.get_all("Lead Category", filters={"is_active": 1, "allow_all_operational_users": 1}, pluck="name"))
    department = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "department")
    if department:
        categories.update(frappe.get_all("Lead Category", filters={"is_active": 1, "department": department}, pluck="name"))
    categories.update(
        frappe.get_all(
            "User Permission",
            filters={"user": user, "allow": "Lead Category"},
            pluck="for_value",
        )
    )
    return sorted(categories)


def crm_lead_query(user=None):
    user = user or frappe.session.user
    if is_management(user):
        return ""
    if not is_operational(user):
        return ""
    categories = accessible_categories(user)
    if not categories:
        return "1=0"
    return "`tabCRM Lead`.`lead_category` in ({})".format(",".join(frappe.db.escape(value) for value in categories))


def crm_lead_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if is_management(user):
        return True
    if not is_operational(user):
        return None
    return doc.get("lead_category") in accessible_categories(user)


def queue_query(user=None):
    return _category_query("Lead Intake Queue", user)


def queue_permission(doc, ptype=None, user=None):
    return _category_permission(doc, user)


def visa_query(user=None):
    return _linked_lead_query("Visa Application", "lead", user)


def visa_permission(doc, ptype=None, user=None):
    return _linked_lead_permission(doc.get("lead"), user)


def communication_event_query(user=None):
    return _linked_lead_query("Communication Event", "lead", user)


def communication_event_permission(doc, ptype=None, user=None):
    return _linked_lead_permission(doc.get("lead"), user)


def todo_query(user=None):
    user = user or frappe.session.user
    if is_management(user):
        return ""
    escaped_user = frappe.db.escape(user)
    return f"(`tabToDo`.`allocated_to`={escaped_user} or `tabToDo`.`owner`={escaped_user})"


def todo_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if is_management(user):
        return True
    return doc.get("allocated_to") == user or doc.get("owner") == user


def email_account_query(user=None):
    user = user or frappe.session.user
    if is_management(user):
        return ""
    return _email_account_condition("tabEmail Account", user)


def email_account_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if is_management(user):
        return True
    return doc.get("name") in _user_email_accounts(user)


def communication_query(user=None):
    user = user or frappe.session.user
    if is_management(user):
        return ""
    user_cond = f"`tabCommunication`.`owner`={frappe.db.escape(user)}"
    email_cond = _email_account_condition("tabCommunication", user)
    lead_cond = _communication_lead_condition(user)
    return f"({user_cond} or {email_cond} or {lead_cond})"


def communication_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if is_management(user):
        return True
    if doc.get("owner") == user:
        return True
    if doc.get("email_account") and doc.get("email_account") in _user_email_accounts(user):
        return True
    if doc.get("reference_doctype") == "CRM Lead" and doc.get("reference_name"):
        return _linked_lead_permission(doc.get("reference_name"), user)
    if doc.get("reference_doctype") == "CRM Deal" and doc.get("reference_name"):
        lead = frappe.db.get_value("CRM Deal", doc.get("reference_name"), "lead")
        return _linked_lead_permission(lead, user)
    return False


def contact_query(user=None):
    user = user or frappe.session.user
    if is_management(user):
        return ""
    escaped_user = frappe.db.escape(user)
    categories = accessible_categories(user)
    if not categories:
        return f"(`tabContact`.`owner`={escaped_user})"
    category_sql = ",".join(frappe.db.escape(value) for value in categories)
    lead_link = f"(`tabContact`.`name` in (select `parent` from `tabDynamic Link` where `parenttype`='Contact' and `link_doctype`='CRM Lead' and `link_name` in (select `name` from `tabCRM Lead` where `lead_category` in ({category_sql}))))"
    return f"(`tabContact`.`owner`={escaped_user} or {lead_link})"


def contact_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if is_management(user):
        return True
    if doc.get("owner") == user:
        return True
    if hasattr(doc, "links") and doc.links:
        for link in doc.links:
            if link.link_doctype == "CRM Lead" and link.link_name:
                if _linked_lead_permission(link.link_name, user):
                    return True
    return False


def crm_organization_query(user=None):
    user = user or frappe.session.user
    if is_management(user):
        return ""
    escaped_user = frappe.db.escape(user)
    return f"(`tabCRM Organization`.`owner`={escaped_user})"


def crm_organization_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if is_management(user):
        return True
    return doc.get("owner") == user


def fcrm_note_query(user=None):
    user = user or frappe.session.user
    if is_management(user):
        return ""
    escaped_user = frappe.db.escape(user)
    categories = accessible_categories(user)
    if not categories:
        return f"(`tabFCRM Note`.`owner`={escaped_user})"
    category_sql = ",".join(frappe.db.escape(value) for value in categories)
    lead_ref = f"(`tabFCRM Note`.`reference_doctype`='CRM Lead' and `tabFCRM Note`.`reference_docname` in (select `name` from `tabCRM Lead` where `lead_category` in ({category_sql})))"
    return f"(`tabFCRM Note`.`owner`={escaped_user} or {lead_ref})"


def fcrm_note_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if is_management(user):
        return True
    if doc.get("owner") == user:
        return True
    if doc.get("reference_doctype") == "CRM Lead" and doc.get("reference_docname"):
        return _linked_lead_permission(doc.get("reference_docname"), user)
    return False


def crm_task_query(user=None):
    user = user or frappe.session.user
    if is_management(user):
        return ""
    escaped_user = frappe.db.escape(user)
    categories = accessible_categories(user)
    if not categories:
        return f"(`tabCRM Task`.`owner`={escaped_user} or `tabCRM Task`.`assigned_to`={escaped_user})"
    category_sql = ",".join(frappe.db.escape(value) for value in categories)
    lead_ref = f"(`tabCRM Task`.`reference_doctype`='CRM Lead' and `tabCRM Task`.`reference_docname` in (select `name` from `tabCRM Lead` where `lead_category` in ({category_sql})))"
    return f"(`tabCRM Task`.`owner`={escaped_user} or `tabCRM Task`.`assigned_to`={escaped_user} or {lead_ref})"


def crm_task_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if is_management(user):
        return True
    if doc.get("owner") == user or doc.get("assigned_to") == user:
        return True
    if doc.get("reference_doctype") == "CRM Lead" and doc.get("reference_docname"):
        return _linked_lead_permission(doc.get("reference_docname"), user)
    return False


def crm_call_log_query(user=None):
    user = user or frappe.session.user
    if is_management(user):
        return ""
    escaped_user = frappe.db.escape(user)
    categories = accessible_categories(user)
    if not categories:
        return f"(`tabCRM Call Log`.`owner`={escaped_user} or `tabCRM Call Log`.`caller`={escaped_user} or `tabCRM Call Log`.`receiver`={escaped_user})"
    category_sql = ",".join(frappe.db.escape(value) for value in categories)
    lead_ref = f"(`tabCRM Call Log`.`reference_doctype`='CRM Lead' and `tabCRM Call Log`.`reference_docname` in (select `name` from `tabCRM Lead` where `lead_category` in ({category_sql})))"
    return f"(`tabCRM Call Log`.`owner`={escaped_user} or `tabCRM Call Log`.`caller`={escaped_user} or `tabCRM Call Log`.`receiver`={escaped_user} or {lead_ref})"


def crm_call_log_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if is_management(user):
        return True
    if doc.get("owner") == user or doc.get("caller") == user or doc.get("receiver") == user:
        return True
    if doc.get("reference_doctype") == "CRM Lead" and doc.get("reference_docname"):
        return _linked_lead_permission(doc.get("reference_docname"), user)
    return False


def whatsapp_message_query(user=None):
    """
    SQL permission query for WhatsApp Message:
    - Management / Admin: full visibility.
    - Counselors: can see their own messages or messages attached to CRM Leads they have permission to access.
    """
    user = user or frappe.session.user
    if is_management(user):
        return ""
    escaped_user = frappe.db.escape(user)
    categories = accessible_categories(user)
    if not categories:
        return f"(`tabWhatsApp Message`.`owner`={escaped_user})"
    category_sql = ",".join(frappe.db.escape(value) for value in categories)
    lead_ref = f"(`tabWhatsApp Message`.`reference_doctype`='CRM Lead' and `tabWhatsApp Message`.`reference_docname` in (select `name` from `tabCRM Lead` where `lead_category` in ({category_sql})))"
    return f"(`tabWhatsApp Message`.`owner`={escaped_user} or {lead_ref})"


def whatsapp_message_permission(doc, ptype=None, user=None):
    """
    Document-level permission check for WhatsApp Message:
    - Management / Admin: full access.
    - Message owner: full access.
    - Linked CRM Lead: scoped by lead permissions.
    """
    user = user or frappe.session.user
    if is_management(user):
        return True
    if doc.get("owner") == user:
        return True
    if doc.get("reference_doctype") == "CRM Lead" and doc.get("reference_docname"):
        return _linked_lead_permission(doc.get("reference_docname"), user)
    if doc.get("reference_doctype") == "Customer" and doc.get("reference_docname"):
        return True
    return False


def customer_query(user=None):
    user = user or frappe.session.user
    if is_management(user):
        return ""
    return ""


def customer_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if is_management(user):
        return True
    return True


def _category_query(doctype, user):
    user = user or frappe.session.user
    if is_management(user):
        return ""
    if not is_operational(user):
        return ""
    categories = accessible_categories(user)
    if not categories:
        return "1=0"
    return "`tab{}`.`lead_category` in ({})".format(doctype, ",".join(frappe.db.escape(value) for value in categories))


def _category_permission(doc, user):
    user = user or frappe.session.user
    if is_management(user):
        return True
    if not is_operational(user):
        return None
    return doc.get("lead_category") in accessible_categories(user)


def _linked_lead_query(table, field, user):
    user = user or frappe.session.user
    if is_management(user):
        return ""
    if not is_operational(user):
        return ""
    categories = accessible_categories(user)
    if not categories:
        return "1=0"
    category_sql = ",".join(frappe.db.escape(value) for value in categories)
    reference = f" or (`tab{table}`.`reference_doctype`='CRM Lead' and `tab{table}`.`reference_docname` in (select `name` from `tabCRM Lead` where `lead_category` in ({category_sql})))" if frappe.get_meta(table).has_field("reference_doctype") else ""
    return f"(`tab{table}`.`{field}` in (select `name` from `tabCRM Lead` where `lead_category` in ({category_sql})){reference})"


def _linked_lead_permission(lead, user):
    if not lead:
        return False
    user = user or frappe.session.user
    if is_management(user):
        return True
    category = frappe.db.get_value("CRM Lead", lead, "lead_category")
    return is_management(user) or category in accessible_categories(user)


def _user_email_accounts(user):
    accounts = set(frappe.get_all("Email Account", filters={"owner": user}, pluck="name"))
    accounts.update(frappe.get_all("Email Account", filters={"connected_user": user}, pluck="name"))
    if frappe.db.exists("DocType", "User Email"):
        accounts.update(frappe.get_all("User Email", filters={"parent": user, "parenttype": "User"}, pluck="email_account"))
    return sorted(value for value in accounts if value)


def _email_account_condition(table, user):
    accounts = _user_email_accounts(user)
    if not accounts:
        return "1=0"
    return f"`{table}`.`email_account` in ({','.join(frappe.db.escape(value) for value in accounts)})"


def _communication_lead_condition(user):
    categories = accessible_categories(user)
    if not categories:
        return "1=0"
    category_sql = ",".join(frappe.db.escape(value) for value in categories)
    direct = f"(`tabCommunication`.`reference_doctype`='CRM Lead' and `tabCommunication`.`reference_name` in (select `name` from `tabCRM Lead` where `lead_category` in ({category_sql})))"
    deal = f"(`tabCommunication`.`reference_doctype`='CRM Deal' and `tabCommunication`.`reference_name` in (select `name` from `tabCRM Deal` where `lead` in (select `name` from `tabCRM Lead` where `lead_category` in ({category_sql}))))"
    return f"({direct} or {deal})"
