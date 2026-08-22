# Copyright (c) 2026, Shahbaz and contributors
# For license information, please see license.txt

import frappe
from visa_crm.patches.setup_suggestion_field import execute as setup_suggestion_field_patch
from visa_crm.api.call_log_hooks import setup_call_log_form_script
from visa_crm.api.doc_overrides import get_data as doc_get_data
from visa_crm.api.task_reminders import send_task_due_reminders
from visa_crm.api.lead_permissions import (
    is_management,
    contact_query,
    contact_permission,
    crm_organization_query,
    crm_organization_permission,
    fcrm_note_query,
    fcrm_note_permission,
    crm_task_query,
    crm_task_permission,
    crm_call_log_query,
    crm_call_log_permission,
)


@frappe.whitelist()
def run_setup_and_migrations():
    """Execute required patches & scripts for Suggestion field and CRM Call Log script"""
    setup_suggestion_field_patch()
    setup_call_log_form_script()

    cf = frappe.db.get_value(
        "Custom Field",
        "CRM Lead-suggestion_or_requirement",
        ["fieldname", "fieldtype", "label"],
        as_dict=True,
    )
    cfs = frappe.db.get_value(
        "CRM Form Script",
        {"dt": "CRM Call Log", "view": "Form"},
        ["name", "enabled"],
        as_dict=True,
    )
    return {
        "ok": True,
        "suggestion_custom_field": cf,
        "call_log_form_script": cfs,
    }


@frappe.whitelist()
def verify_like_filter(search_term="Yaseen"):
    """Test CRM Lead 'Like' filter normalization with search term"""
    data = doc_get_data(
        doctype="CRM Lead",
        filters={"name": ["LIKE", f"%{search_term}%"]},
        order_by="modified desc",
        page_length=5,
    )
    leads = data.get("data", []) if isinstance(data, dict) else []
    results = [
        {
            "name": l.get("name"),
            "lead_name": l.get("lead_name"),
            "first_name": l.get("first_name"),
            "mobile_no": l.get("mobile_no"),
            "status": l.get("status"),
        }
        for l in leads[:5]
    ]
    return {
        "ok": True,
        "search_term": search_term,
        "matching_count": len(leads),
        "sample_leads": results,
    }


@frappe.whitelist()
def verify_task_reminders():
    """Trigger task reminder scan and check generated notifications"""
    scan_res = send_task_due_reminders()
    recent_notifs = frappe.get_all(
        "CRM Notification",
        filters={"type": "Task"},
        fields=["name", "to_user", "message", "notification_type_doc", "creation"],
        order_by="creation desc",
        limit=5,
    )
    return {
        "ok": True,
        "scan_result": scan_res,
        "recent_task_notifications": recent_notifs,
    }


@frappe.whitelist()
def verify_contacts_columns():
    """Test Contacts list dynamic enrichment (Customer Name, Category, Subcategory)"""
    data = doc_get_data(
        doctype="Contact",
        filters={},
        order_by="modified desc",
        page_length=5,
    )
    contacts = data.get("data", []) if isinstance(data, dict) else []
    results = [
        {
            "name": c.get("name"),
            "full_name": c.get("full_name"),
            "customer_name": c.get("customer_name"),
            "lead_category": c.get("lead_category"),
            "lead_group": c.get("lead_group"),
            "email_id": c.get("email_id"),
        }
        for c in contacts[:5]
    ]
    return {
        "ok": True,
        "total_returned": len(contacts),
        "sample_contacts": results,
    }


@frappe.whitelist()
def verify_role_based_permissions():
    """Test role-based sidebar visibility and document access boundaries"""
    admin_user = "Administrator"
    counselor_users = frappe.get_all(
        "Has Role",
        filters={"role": "Sales User", "parent": ["!=", "Administrator"]},
        pluck="parent",
        limit=2,
    )
    normal_user = counselor_users[0] if counselor_users else "test_counselor"

    admin_contact_q = contact_query(admin_user)
    normal_contact_q = contact_query(normal_user)
    normal_task_q = crm_task_query(normal_user)
    normal_call_q = crm_call_log_query(normal_user)

    dummy_doc_other = frappe._dict({
        "owner": "other_employee@middleeast.com",
        "assigned_to": "other_employee@middleeast.com",
        "caller": "other_employee@middleeast.com",
        "receiver": "customer@middleeast.com",
    })

    admin_access = contact_permission(dummy_doc_other, user="Administrator")
    normal_access = contact_permission(dummy_doc_other, user=normal_user)

    return {
        "ok": True,
        "admin_user": admin_user,
        "normal_user": normal_user,
        "admin_contact_query": admin_contact_q,
        "normal_contact_query": normal_contact_q,
        "normal_task_query": normal_task_q,
        "normal_call_query": normal_call_q,
        "can_admin_access_other_record": admin_access,
        "can_normal_access_other_record": normal_access,
        "counts": {
            "contacts": frappe.db.count("Contact"),
            "crm_tasks": frappe.db.count("CRM Task"),
            "crm_call_logs": frappe.db.count("CRM Call Log"),
            "fcrm_notes": frappe.db.count("FCRM Note"),
            "crm_orgs": frappe.db.count("CRM Organization"),
        },
    }


@frappe.whitelist()
def run_all_verifications():
    """Runs all 5 verification suites in a single whitelisted call"""
    m = run_setup_and_migrations()
    l = verify_like_filter("Yaseen")
    t = verify_task_reminders()
    c = verify_contacts_columns()
    p = verify_role_based_permissions()
    return {
        "ok": True,
        "migrations": m,
        "like_filter": l,
        "task_reminders": t,
        "contacts_columns": c,
        "role_permissions": p,
    }
