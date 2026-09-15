# Copyright (c) 2026, Shahbaz and contributors
# For license information, please see license.txt

import frappe
from crm.fcrm.doctype.crm_deal.crm_deal import CRMDeal


class VisaCRMDeal(CRMDeal):
    """
    Subclass of CRMDeal providing rich staff-friendly default list view columns
    including Customer Name, Mobile, Email, Campaign, Category, Destination, Department, Value.
    """

    @staticmethod
    def default_list_data():
        return {
            "columns": [
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
            ],
            "rows": [
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
            ],
        }
