import frappe
from frappe.utils import cint


DEFAULT_MANAGEMENT_ROLES = {"System Manager", "Sales Manager", "General Manager", "Managing Director", "MD", "CRM Manager"}
DEFAULT_OPERATIONAL_ROLES = {"Sales User", "Counselor", "Visa Processing", "Lead Team", "Inbox User"}


def management_roles():
    configured = frappe.conf.get("visa_crm_management_roles") or []
    if isinstance(configured, str):
        configured = [role.strip() for role in configured.split(",") if role.strip()]
    return DEFAULT_MANAGEMENT_ROLES | set(configured)


def is_management(user=None):
    user = user or frappe.session.user
    return user == "Administrator" or bool(management_roles() & set(frappe.get_roles(user)))


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


def customer_query(user=None):
    return _linked_lead_query("Customer", "crm_lead", user)


def customer_permission(doc, ptype=None, user=None):
    return _linked_lead_permission(doc.get("crm_lead"), user)


def communication_event_query(user=None):
    user = user or frappe.session.user
    if is_management(user):
        return ""
    if not is_operational(user):
        return ""
    lead_condition = _linked_lead_sql("tabCommunication Event", "lead", user)
    return f"({lead_condition} or `tabCommunication Event`.`assigned_user`={frappe.db.escape(user)} or `tabCommunication Event`.`owner`={frappe.db.escape(user)})"


def communication_event_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if is_management(user):
        return True
    if not is_operational(user):
        return None
    if doc.get("assigned_user") == user or doc.get("owner") == user:
        return True
    return _linked_lead_permission(doc.get("lead"), user)


def todo_query(user=None):
    user = user or frappe.session.user
    if is_management(user):
        return ""
    if not is_operational(user):
        return ""
    lead_condition = _linked_lead_sql("tabToDo", "reference_name", user, reference_type="CRM Lead")
    return f"(`tabToDo`.`allocated_to`={frappe.db.escape(user)} or `tabToDo`.`assigned_by`={frappe.db.escape(user)} or {lead_condition})"


def todo_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if is_management(user):
        return True
    if not is_operational(user):
        return None
    if doc.get("allocated_to") == user or doc.get("assigned_by") == user:
        return True
    if doc.get("reference_type") == "CRM Lead":
        return _linked_lead_permission(doc.get("reference_name"), user)
    return None


def email_account_query(user=None):
    user = user or frappe.session.user
    if is_management(user):
        return ""
    if not is_operational(user):
        return ""
    allowed = _user_email_accounts(user)
    conditions = [f"`tabEmail Account`.`owner`={frappe.db.escape(user)}", f"`tabEmail Account`.`connected_user`={frappe.db.escape(user)}"]
    if allowed:
        conditions.append("`tabEmail Account`.`name` in ({})".format(",".join(frappe.db.escape(value) for value in allowed)))
    return "(" + " or ".join(conditions) + ")"


def email_account_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if is_management(user):
        return True
    if not is_operational(user):
        return None
    return doc.get("owner") == user or doc.get("connected_user") == user or doc.name in _user_email_accounts(user)


def communication_query(user=None):
    user = user or frappe.session.user
    if is_management(user):
        return ""
    if not is_operational(user):
        return ""
    account_condition = _email_account_condition("tabCommunication", user)
    lead_condition = _communication_lead_condition(user)
    return f"(`tabCommunication`.`owner`={frappe.db.escape(user)} or {account_condition} or {lead_condition})"


def communication_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if is_management(user):
        return True
    if not is_operational(user):
        return None
    if doc.get("owner") == user or doc.get("email_account") in _user_email_accounts(user):
        return True
    if doc.get("reference_doctype") == "CRM Lead":
        return _linked_lead_permission(doc.get("reference_name"), user)
    if doc.get("reference_doctype") == "CRM Deal":
        lead = frappe.db.get_value("CRM Deal", doc.get("reference_name"), "lead")
        return _linked_lead_permission(lead, user)
    return False


def _category_query(doctype, user=None):
    user = user or frappe.session.user
    if is_management(user):
        return ""
    if not is_operational(user):
        return ""
    categories = accessible_categories(user)
    if not categories:
        return "1=0"
    return "`tab{}`.`lead_category` in ({})".format(doctype, ",".join(frappe.db.escape(value) for value in categories))


def _category_permission(doc, user=None):
    user = user or frappe.session.user
    if is_management(user):
        return True
    if not is_operational(user):
        return None
    return doc.get("lead_category") in accessible_categories(user)


def _linked_lead_query(doctype, field, user=None):
    user = user or frappe.session.user
    if is_management(user):
        return ""
    if not is_operational(user):
        return ""
    return _linked_lead_sql(f"tab{doctype}", field, user)


def _linked_lead_sql(table, field, user=None, reference_type=None):
    user = user or frappe.session.user
    categories = accessible_categories(user)
    if not categories:
        return "1=0"
    category_sql = ",".join(frappe.db.escape(value) for value in categories)
    reference = f" and `{table}`.`reference_type`='CRM Lead'" if reference_type else ""
    return f"(`{table}`.`{field}` in (select `name` from `tabCRM Lead` where `lead_category` in ({category_sql})){reference})"


def _linked_lead_permission(lead, user=None):
    if not is_operational(user):
        return None
    if not lead or not frappe.db.exists("CRM Lead", lead):
        return False
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
