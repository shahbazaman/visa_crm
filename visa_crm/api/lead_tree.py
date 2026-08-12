import frappe
import json
from frappe import _

UNSET_CATEGORY_VALUES = ["", "Uncategorized"]
UNSET_SUBCATEGORY_VALUES = ["", "Unspecified", "No Subcategory"]

@frappe.whitelist()
def get_lead_tree_nodes(parent_level=None, category=None, subcategory=None, filters=None):
    """
    Returns nodes for the CRM Lead Tree View.
    Enforces standard CRM Lead permissions by using frappe.get_list.
    """
    if filters and isinstance(filters, str):
        filters = json.loads(filters)
    if not filters:
        filters = {}

    if parent_level == "Categories" or not parent_level:
        return _get_categories(filters)
    elif parent_level == "Subcategories":
        return _get_subcategories(category, filters)
    elif parent_level == "Leads":
        return _get_leads(category, subcategory, filters)
    else:
        return []

def _build_orm_filters(filters, category=None, subcategory=None):
    orm_filters = []
    
    if filters.get("status"):
        orm_filters.append(["CRM Lead", "status", "in", filters["status"]])
    if filters.get("owner"):
        orm_filters.append(["CRM Lead", "lead_owner", "in", filters["owner"]])
    if filters.get("lead_category"):
        orm_filters.append(["CRM Lead", "lead_category", "in", filters.get("lead_category")])
    if filters.get("lead_group"):
        orm_filters.append(["CRM Lead", "lead_group", "in", filters.get("lead_group")])

    if category == "Uncategorized":
        orm_filters.append(["CRM Lead", "ifnull(lead_category, '')", "in", UNSET_CATEGORY_VALUES])
    elif category:
        orm_filters.append(["CRM Lead", "lead_category", "=", category])

    if subcategory == "No Subcategory":
        orm_filters.append(["CRM Lead", "ifnull(lead_group, '')", "in", UNSET_SUBCATEGORY_VALUES])
    elif subcategory:
        orm_filters.append(["CRM Lead", "lead_group", "=", subcategory])

    or_filters = []
    search_term = filters.get("search")
    if search_term:
        or_filters = [
            ["CRM Lead", "name", "like", f"%{search_term}%"],
            ["CRM Lead", "lead_name", "like", f"%{search_term}%"],
            ["CRM Lead", "mobile_no", "like", f"%{search_term}%"],
            ["CRM Lead", "email", "like", f"%{search_term}%"],
        ]
        
    return or_filters, orm_filters

def _get_categories(filters):
    or_filters, orm_filters = _build_orm_filters(filters)
    
    leads = frappe.get_list(
        "CRM Lead",
        filters=orm_filters,
        or_filters=or_filters,
        fields=["lead_category", "count(name) as count"],
        group_by="lead_category",
        order_by="lead_category asc"
    )

    merged_nodes = {}
    for row in leads:
        raw_cat = row.get("lead_category")
        cat_name = "Uncategorized" if not raw_cat or raw_cat in UNSET_CATEGORY_VALUES else raw_cat
        count = row.get("count", 0)
        if cat_name in merged_nodes:
            merged_nodes[cat_name]["count"] += count
        else:
            merged_nodes[cat_name] = {
                "value": cat_name,
                "label": cat_name,
                "expandable": True,
                "level": "Category",
                "count": count
            }
            
    return list(merged_nodes.values())

def _get_subcategories(category, filters):
    or_filters, orm_filters = _build_orm_filters(filters, category=category)
    
    leads = frappe.get_list(
        "CRM Lead",
        filters=orm_filters,
        or_filters=or_filters,
        fields=["lead_group", "count(name) as count"],
        group_by="lead_group",
        order_by="lead_group asc"
    )

    merged_nodes = {}
    for row in leads:
        raw_sub = row.get("lead_group")
        sub_name = "No Subcategory" if not raw_sub or raw_sub in UNSET_SUBCATEGORY_VALUES else raw_sub
        count = row.get("count", 0)
        if sub_name in merged_nodes:
            merged_nodes[sub_name]["count"] += count
        else:
            merged_nodes[sub_name] = {
                "value": sub_name,
                "label": sub_name,
                "expandable": True,
                "level": "Subcategory",
                "count": count
            }
            
    return list(merged_nodes.values())

def _get_leads(category, subcategory, filters):
    or_filters, orm_filters = _build_orm_filters(filters, category=category, subcategory=subcategory)
    
    page = int(filters.get("page", 1))
    page_length = int(filters.get("page_length", 20))
    start = (page - 1) * page_length

    # Validate sorting
    sort_by = filters.get("sort_by", "modified")
    sort_order = filters.get("sort_order", "desc")
    
    allowed_sort_fields = ["name", "modified", "creation", "lead_name", "status"]
    if sort_by not in allowed_sort_fields:
        sort_by = "modified"
    if sort_order.lower() not in ["asc", "desc"]:
        sort_order = "desc"

    order_by = f"{sort_by} {sort_order}"

    fields = [
        "name", "lead_name", "status", "lead_owner", "creation", "modified",
        "image", "first_name", "organization", "website", "sla_status",
        "response_by", "first_responded_on", "mobile_no", "email", "meta_campaign_name",
        "first_response_time", "_assign", "_liked_by",
        "_email_count", "_note_count", "_task_count", "_comment_count"
    ]

    leads = frappe.get_list(
        "CRM Lead",
        filters=orm_filters,
        or_filters=or_filters,
        fields=fields,
        order_by=order_by,
        limit_start=start,
        limit_page_length=page_length + 1
    )

    has_more = len(leads) > page_length
    if has_more:
        leads.pop()

    return {
        "data": leads,
        "has_more": has_more,
        "page": page,
        "page_length": page_length
    }
