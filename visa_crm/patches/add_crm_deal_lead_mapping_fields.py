# Copyright (c) 2026, Shahbaz and contributors
# For license information, please see license.txt

import json
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CUSTOM_FIELDS = [
    {
        "fieldname": "custom_meta_campaign_name",
        "label": "Campaign Name",
        "fieldtype": "Data",
        "fetch_from": "lead.meta_campaign_name",
        "read_only": 1,
        "in_list_view": 1,
        "in_standard_filter": 1,
        "insert_after": "source",
    },
    {
        "fieldname": "custom_meta_campaign_id",
        "label": "Campaign ID",
        "fieldtype": "Data",
        "fetch_from": "lead.meta_campaign_id",
        "read_only": 1,
        "insert_after": "custom_meta_campaign_name",
    },
    {
        "fieldname": "custom_meta_adset_name",
        "label": "Ad Set Name",
        "fieldtype": "Data",
        "fetch_from": "lead.meta_adset_name",
        "read_only": 1,
        "in_list_view": 1,
        "in_standard_filter": 1,
        "insert_after": "custom_meta_campaign_id",
    },
    {
        "fieldname": "custom_meta_adset_id",
        "label": "Ad Set ID",
        "fieldtype": "Data",
        "fetch_from": "lead.meta_adset_id",
        "read_only": 1,
        "insert_after": "custom_meta_adset_name",
    },
    {
        "fieldname": "custom_meta_ad_name",
        "label": "Ad Name",
        "fieldtype": "Data",
        "fetch_from": "lead.meta_ad_name",
        "read_only": 1,
        "insert_after": "custom_meta_adset_id",
    },
    {
        "fieldname": "custom_meta_ad_id",
        "label": "Ad ID",
        "fieldtype": "Data",
        "fetch_from": "lead.meta_ad_id",
        "read_only": 1,
        "insert_after": "custom_meta_ad_name",
    },
    {
        "fieldname": "custom_facebook_form_id",
        "label": "Facebook Form ID",
        "fieldtype": "Data",
        "fetch_from": "lead.facebook_form_id",
        "read_only": 1,
        "insert_after": "custom_meta_ad_id",
    },
    {
        "fieldname": "custom_facebook_lead_id",
        "label": "Facebook Lead ID",
        "fieldtype": "Data",
        "fetch_from": "lead.facebook_lead_id",
        "read_only": 1,
        "insert_after": "custom_facebook_form_id",
    },
    {
        "fieldname": "custom_lead_category",
        "label": "Lead Category",
        "fieldtype": "Data",
        "fetch_from": "lead.lead_category",
        "in_list_view": 1,
        "in_standard_filter": 1,
        "insert_after": "custom_facebook_lead_id",
    },
    {
        "fieldname": "custom_lead_group",
        "label": "Lead Group",
        "fieldtype": "Data",
        "fetch_from": "lead.lead_group",
        "insert_after": "custom_lead_category",
    },
    {
        "fieldname": "custom_responsible_department",
        "label": "Responsible Department",
        "fieldtype": "Link",
        "options": "Department",
        "fetch_from": "lead.responsible_department",
        "in_list_view": 1,
        "in_standard_filter": 1,
        "insert_after": "custom_lead_group",
    },
    {
        "fieldname": "custom_destination",
        "label": "Destination",
        "fieldtype": "Data",
        "fetch_from": "lead.custom_destination",
        "in_list_view": 1,
        "in_standard_filter": 1,
        "insert_after": "custom_responsible_department",
    },
    {
        "fieldname": "custom_visa_type",
        "label": "Visa Type",
        "fieldtype": "Data",
        "fetch_from": "lead.custom_visa_type",
        "insert_after": "custom_destination",
    },
    {
        "fieldname": "custom_travel_month",
        "label": "Travel Month",
        "fieldtype": "Data",
        "fetch_from": "lead.custom_travel_month",
        "insert_after": "custom_visa_type",
    },
    {
        "fieldname": "custom_budget",
        "label": "Budget",
        "fieldtype": "Data",
        "fetch_from": "lead.custom_budget",
        "insert_after": "custom_travel_month",
    },
    {
        "fieldname": "custom_assigned_counselor",
        "label": "Assigned Counselor",
        "fieldtype": "Link",
        "options": "Employee",
        "fetch_from": "lead.assigned_counselor",
        "insert_after": "custom_budget",
    },
    {
        "fieldname": "custom_customer",
        "label": "Customer",
        "fieldtype": "Link",
        "options": "Customer",
        "fetch_from": "lead.customer",
        "insert_after": "custom_assigned_counselor",
    },
]


def execute():
    """
    Idempotent migration:
    1. Adds custom fields to CRM Deal.
    2. Configures default CRM View Settings for CRM Deal with 14 rich columns.
    3. Updates CRM Fields Layout side panel for CRM Deal.
    """
    if not frappe.db.exists("DocType", "CRM Deal"):
        return

    # 1. Add custom fields
    meta = frappe.get_meta("CRM Deal")
    fields_to_create = []
    for f in CUSTOM_FIELDS:
        if not meta.has_field(f["fieldname"]):
            fields_to_create.append(f)

    if fields_to_create:
        create_custom_fields({"CRM Deal": fields_to_create}, update=True)

    # 2. Setup standard CRM View Settings for CRM Deal List
    setup_crm_deal_view_settings()

    # 3. Setup Side Panel fields layout
    setup_deal_sidepanel_layout()

    frappe.db.commit()


def setup_crm_deal_view_settings():
    if not frappe.db.exists("DocType", "CRM View Settings"):
        return

    columns = [
        {"label": "Customer / Lead", "type": "Data", "key": "lead_name", "width": "13rem"},
        {"label": "Mobile No.", "type": "Data", "key": "mobile_no", "width": "11rem"},
        {"label": "Email", "type": "Data", "key": "email", "width": "12rem"},
        {"label": "Source", "type": "Link", "key": "source", "options": "CRM Lead Source", "width": "9rem"},
        {"label": "Campaign Name", "type": "Data", "key": "custom_meta_campaign_name", "width": "13rem"},
        {"label": "Ad Set Name", "type": "Data", "key": "custom_meta_adset_name", "width": "10rem"},
        {"label": "Category", "type": "Data", "key": "custom_lead_category", "width": "9rem"},
        {"label": "Destination", "type": "Data", "key": "custom_destination", "width": "9rem"},
        {"label": "Department", "type": "Link", "key": "custom_responsible_department", "options": "Department", "width": "11rem"},
        {"label": "Status", "type": "Link", "key": "status", "options": "CRM Deal Status", "width": "9rem"},
        {"label": "Deal Owner", "type": "Link", "key": "deal_owner", "options": "User", "width": "10rem"},
        {"label": "Deal Value", "type": "Currency", "key": "expected_deal_value", "align": "right", "width": "9rem"},
        {"label": "Expected Closure", "type": "Date", "key": "expected_closure_date", "width": "10rem"},
        {"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
    ]

    rows = [
        "name",
        "lead_name",
        "first_name",
        "last_name",
        "email",
        "mobile_no",
        "phone",
        "source",
        "custom_meta_campaign_name",
        "custom_meta_adset_name",
        "custom_lead_category",
        "custom_destination",
        "custom_visa_type",
        "custom_responsible_department",
        "status",
        "deal_owner",
        "expected_deal_value",
        "annual_revenue",
        "currency",
        "expected_closure_date",
        "modified",
        "creation",
        "lead",
        "organization",
        "organization_name",
        "_assign",
    ]

    # Create/update global standard view (user="")
    view_name = frappe.db.get_value("CRM View Settings", {"dt": "CRM Deal", "type": "list", "is_standard": 1, "user": ""}, "name")
    if view_name:
        doc = frappe.get_doc("CRM View Settings", view_name)
        doc.label = "Deals"
        doc.columns = json.dumps(columns)
        doc.rows = json.dumps(rows)
        doc.is_standard = 1
        doc.is_default = 1
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.new_doc("CRM View Settings")
        doc.label = "Deals"
        doc.dt = "CRM Deal"
        doc.type = "list"
        doc.route_name = "Deals"
        doc.user = ""
        doc.is_standard = 1
        doc.is_default = 1
        doc.columns = json.dumps(columns)
        doc.rows = json.dumps(rows)
        doc.order_by = "modified desc"
        doc.filters = "{}"
        doc.insert(ignore_permissions=True)


def setup_deal_sidepanel_layout():
    if not frappe.db.exists("DocType", "CRM Fields Layout"):
        return

    layout_name = frappe.db.get_value("CRM Fields Layout", {"dt": "CRM Deal", "type": "Side Panel"}, "name")
    if not layout_name:
        return

    doc = frappe.get_doc("CRM Fields Layout", layout_name)
    layout = json.loads(doc.layout or "[]")

    campaign_fields = [
        "lead",
        "custom_meta_campaign_name",
        "custom_meta_adset_name",
        "custom_meta_ad_name",
        "custom_lead_category",
        "custom_destination",
        "custom_visa_type",
        "custom_travel_month",
        "custom_budget",
        "custom_responsible_department",
        "custom_assigned_counselor",
        "custom_customer",
    ]

    # Check if section already added
    has_campaign_section = any(
        s.get("name") == "lead_campaign_section" or s.get("label") == "Lead & Campaign Details"
        for s in layout
    )

    if not has_campaign_section:
        layout.append({
            "label": "Lead & Campaign Details",
            "name": "lead_campaign_section",
            "opened": True,
            "columns": [
                {
                    "name": "col_campaign_details",
                    "fields": campaign_fields,
                }
            ],
        })
        doc.layout = json.dumps(layout)
        doc.save(ignore_permissions=True)
