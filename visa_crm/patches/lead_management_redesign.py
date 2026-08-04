import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field
from frappe.utils import now_datetime

from visa_crm.api.lead_classification import CLASSIFICATION_FIELDS, classify_payload, classify_queue, sync_lead_classification
from visa_crm.api.meta_utils import has_doctype, has_field, load_json
from visa_crm.api.pipeline_engine import ensure_stage_ledger, rollup_queue
from visa_crm.api.stage_definitions import STAGES


FIELDS = (
    {"fieldname": "lead_category", "label": "Lead Category", "fieldtype": "Link", "options": "Lead Category", "read_only": 1},
    {"fieldname": "lead_group", "label": "Lead Group", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "responsible_department", "label": "Responsible Department", "fieldtype": "Link", "options": "Department", "read_only": 1},
    {"fieldname": "classification_source", "label": "Classification Source", "fieldtype": "Select", "options": "Automatic\nManual", "read_only": 1},
    {"fieldname": "classification_status", "label": "Classification Status", "fieldtype": "Select", "options": "Classified\nNeeds Review\nFailed", "read_only": 1},
    {"fieldname": "classification_rule", "label": "Classification Rule", "fieldtype": "Link", "options": "Lead Classification Rule", "read_only": 1},
    {"fieldname": "classification_reason", "label": "Classification Reason", "fieldtype": "Small Text", "read_only": 1},
    {"fieldname": "classified_at", "label": "Classified At", "fieldtype": "Datetime", "read_only": 1},
    {"fieldname": "classified_by", "label": "Classified By", "fieldtype": "Link", "options": "User", "read_only": 1},
)

CATEGORIES = (
    ("Global Visa", "global-visa", "Global visa - MEH", 10, "Active", 0, 0),
    ("Holidays", "holidays", "Holidays - MEH", 20, "Active", 0, 0),
    ("Reservation", "reservation", "Reservation - MEH", 30, "Active", 0, 0),
    ("Google Ads", "google-ads", "digital marketer - MEH", 40, "Future", 0, 0),
    ("Uncategorized", "uncategorized", None, 90, "Active", 1, 1),
)

RULES = (
    ("WhatsApp to Reservation", 10, "WhatsApp", "Source", "Equals", "WhatsApp", "Reservation", "WhatsApp inquiry"),
    ("Meta Visa Campaign", 100, "Meta", "Campaign Name", "Ends With", "visa", "Global Visa", "Meta campaign ends with visa"),
    ("Meta Package Campaign", 110, "Meta", "Campaign Name", "Ends With", "package", "Holidays", "Meta campaign ends with package"),
    ("Future Google Ads", 20, "Google Ads", "Source", "Equals", "Google Ads", "Google Ads", "Future Google Ads source"),
)


def execute():
    _repair_stage_options()
    _fields()
    _repair_operational_permissions()
    _seed_categories()
    _seed_rules()
    _indexes()
    _backfill()
    _secure_existing_email_accounts()
    _workspace_shortcut()
    frappe.clear_cache()
    frappe.db.commit()


def _repair_stage_options():
    if not has_doctype("Lead Intake Stage"):
        return
    options = "\n".join(row["stage"] for row in STAGES)
    filters = {"parent": "Lead Intake Stage", "fieldname": "stage"}
    if frappe.db.exists("DocField", filters):
        frappe.db.set_value("DocField", filters, "options", options, update_modified=False)
        frappe.clear_cache(doctype="Lead Intake Stage")


def _repair_operational_permissions():
    if not has_doctype("CRM Lead") or not frappe.db.exists("Custom DocPerm", {"parent": "CRM Lead"}):
        return
    for role in ("Sales User", "Counselor", "Visa Processing", "Lead Team"):
        if not frappe.db.exists("Role", role) or frappe.db.exists(
            "Custom DocPerm", {"parent": "CRM Lead", "role": role, "permlevel": 0, "if_owner": 0}
        ):
            continue
        frappe.get_doc({
            "doctype": "Custom DocPerm",
            "parent": "CRM Lead",
            "parenttype": "DocType",
            "parentfield": "permissions",
            "role": role,
            "permlevel": 0,
            "read": 1,
            "write": 1,
            "create": 1,
            "email": 1,
            "print": 1,
            "report": 1,
            "export": 1,
        }).insert(ignore_permissions=True)
    frappe.clear_cache(doctype="CRM Lead")


def _fields():
    for doctype in ("CRM Lead", "Lead Intake Queue"):
        if not has_doctype(doctype):
            continue
        insert_after = "meta_campaign_name" if doctype == "CRM Lead" else "campaign_name"
        for definition in FIELDS:
            if has_field(doctype, definition["fieldname"]):
                custom_field = f"{doctype}-{definition['fieldname']}"
                if frappe.db.exists("Custom Field", custom_field):
                    repairs = {
                        field: value
                        for field, value in definition.items()
                        if field in ("label", "options", "read_only")
                        and frappe.db.get_value("Custom Field", custom_field, field) != value
                    }
                    if repairs:
                        frappe.db.set_value("Custom Field", custom_field, repairs, update_modified=False)
                insert_after = definition["fieldname"]
                continue
            field = dict(definition)
            field["insert_after"] = insert_after
            create_custom_field(doctype, field)
            insert_after = field["fieldname"]
        frappe.clear_cache(doctype=doctype)


def _seed_categories():
    for name, key, department, order, status, uncategorized, shared in CATEGORIES:
        values = {
            "category_name": name,
            "category_key": key,
            "is_active": 1,
            "operational_status": status,
            "sort_order": order,
            "department": department if department and frappe.db.exists("Department", department) else None,
            "is_uncategorized": uncategorized,
            "allow_all_operational_users": shared,
        }
        if frappe.db.exists("Lead Category", name):
            current = frappe.db.get_value("Lead Category", name, list(values), as_dict=True) or {}
            missing = {
                field: value
                for field, value in values.items()
                if value is not None and field in ("category_name", "category_key", "department") and not current.get(field)
            }
            if name == "Uncategorized":
                missing.update({"is_active": 1, "is_uncategorized": 1, "allow_all_operational_users": 1})
            if missing:
                frappe.db.set_value("Lead Category", name, missing, update_modified=False)
            continue
        frappe.get_doc({"doctype": "Lead Category", **values}).insert(ignore_permissions=True)
        if department and not values["department"]:
            frappe.logger("visa_crm.migration").warning({"event": "lead_category_department_unmapped", "category": name, "expected_department": department})


def _seed_rules():
    for name, priority, source, field, match_type, value, category, reason in RULES:
        enabled = 0 if category == "Google Ads" else 1
        values = {"rule_name": name, "priority": priority, "source_channel": source, "match_field": field, "match_type": match_type, "match_value": value, "category": category, "reason": reason, "enabled": enabled}
        if frappe.db.exists("Lead Classification Rule", name):
            continue
        frappe.get_doc({"doctype": "Lead Classification Rule", **values}).insert(ignore_permissions=True)


def _indexes():
    for doctype, fields, name in (
        ("CRM Lead", ["lead_category", "lead_group", "creation"], "idx_vc_lead_category_group"),
        ("CRM Lead", ["responsible_department", "lead_category"], "idx_vc_lead_department"),
        ("Lead Intake Queue", ["lead_category", "lead_group"], "idx_vc_queue_category_group"),
        ("Lead Classification Rule", ["enabled", "priority"], "idx_vc_classification_rule"),
        ("Lead Classification History", ["lead", "changed_at"], "idx_vc_classification_history"),
    ):
        if has_doctype(doctype) and all(field in ("name", "creation", "modified") or has_field(doctype, field) for field in fields) and not _index_exists(doctype, name):
            frappe.db.add_index(doctype, fields, index_name=name)


def _backfill():
    queue_fields = ["name", "matched_lead", "lead_source", "normalized_payload"] + [field for field in ("source_lead_id", "customer_name", "phone", "email", "country_interested", "visa_type", "campaign_name", "campaign_id", "form_id", "page_id", "lead_category", "classification_source") if has_field("Lead Intake Queue", field)]
    linked_leads = set()
    for queue in frappe.get_all("Lead Intake Queue", fields=queue_fields, order_by="creation asc", page_length=0):
        ensure_stage_ledger(queue.name)
        if queue.get("matched_lead"):
            linked_leads.add(queue.matched_lead)
        try:
            result = classify_queue(queue.name)
            frappe.db.set_value("Lead Intake Stage", f"{queue.name}:CLASSIFICATION", {"state": "COMPLETED", "completed_at": now_datetime(), "result_doctype": "Lead Category", "result_name": result.get("result_name"), "last_error": None, "last_traceback": None}, update_modified=False)
            rollup_queue(queue.name)
        except Exception:
            frappe.db.set_value("Lead Intake Stage", f"{queue.name}:CLASSIFICATION", {"state": "FAILED", "last_error": "Historical classification backfill failed", "last_traceback": frappe.get_traceback()}, update_modified=False)
            frappe.logger("visa_crm.migration").error({"event": "lead_classification_backfill_failed", "queue": queue.name, "traceback": frappe.get_traceback()})

    lead_fields = ["name", "source", "visa_type", "custom_visa_type", "country", "country_interested", "facebook_lead_id", "facebook_form_id", "meta_campaign_id", "meta_campaign_name", "lead_category", "classification_source"]
    for lead in frappe.get_all("CRM Lead", fields=[field for field in lead_fields if field == "name" or has_field("CRM Lead", field)], page_length=0):
        if lead.name in linked_leads or lead.get("classification_source") == "Manual" and lead.get("lead_category"):
            continue
        result = classify_payload(dict(lead), lead.get("source"))
        sync_lead_classification(lead.name, result, overwrite_automatic=True)


def _secure_existing_email_accounts():
    if not has_doctype("Email Account"):
        return
    fields = ["name"] + [field for field in ("create_lead_from_incoming_email", "append_to", "create_contact") if has_field("Email Account", field)]
    for account in frappe.get_all("Email Account", fields=fields, page_length=0):
        values = {}
        if has_field("Email Account", "create_lead_from_incoming_email"):
            values["create_lead_from_incoming_email"] = 0
        if account.get("append_to") == "CRM Lead":
            values["append_to"] = None
        if has_field("Email Account", "create_contact"):
            values["create_contact"] = 0
        if values:
            frappe.db.set_value("Email Account", account.name, values, update_modified=False)
    if has_doctype("IMAP Folder"):
        frappe.db.sql("update `tabIMAP Folder` set append_to=null where append_to='CRM Lead'")


def _workspace_shortcut():
    if not frappe.db.exists("Workspace", "Visa CRM") or not frappe.db.exists("Page", "lead-management"):
        return
    workspace = frappe.get_doc("Workspace", "Visa CRM")
    if any(row.label == "Lead Management" for row in workspace.get("shortcuts") or []):
        return
    workspace.append("shortcuts", {"label": "Lead Management", "type": "Page", "link_to": "lead-management", "link_type": "Page"})
    workspace.save(ignore_permissions=True)


def _index_exists(doctype, name):
    return any(row.Key_name == name for row in frappe.db.sql(f"show index from `tab{doctype}`", as_dict=True))
