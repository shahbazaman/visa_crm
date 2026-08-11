import frappe
from frappe.utils import cint, getdate, now_datetime

from visa_crm.api.lead_classification import apply_manual_classification
from visa_crm.api.lead_permissions import accessible_categories, is_management, is_operational, require_management


LEAD_FIELDS = [
    "name", "lead_name", "first_name", "last_name", "mobile_no", "phone", "email", "status", "lead_owner",
    "source", "visa_type", "custom_visa_type", "country", "country_interested", "facebook_lead_id",
    "facebook_form_id", "meta_campaign_name", "meta_campaign_id", "lead_category", "lead_group",
    "responsible_department", "classification_source", "classification_status", "classification_reason",
    "classified_at", "creation", "modified", "assigned_counselor", "assigned_employee",
]
STANDARD_DOCUMENT_FIELDS = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx"}


@frappe.whitelist()
def dashboard():
    _require_operational()
    categories = _categories()
    leads = _permitted_leads()
    _add_operational_flags(leads)
    by_category = {category.name: [] for category in categories}
    for lead in leads:
        by_category.setdefault(lead.get("lead_category") or "Uncategorized", []).append(lead)
    cards = []
    for category in categories:
        rows = by_category.get(category.name, [])
        cards.append({
            **category,
            "total": len(rows),
            "new": sum(1 for row in rows if _is_new(row)),
            "unassigned": sum(1 for row in rows if _is_unassigned(row)),
            "overdue": sum(1 for row in rows if row.get("overdue_followup")),
            "needs_attention": sum(1 for row in rows if row.get("needs_attention")),
            "retrying": sum(1 for row in rows if row.get("retrying")),
            "failed": sum(1 for row in rows if row.get("pipeline_failed")),
            "latest": max((row.get("creation") for row in rows if row.get("creation")), default=None),
        })
    summary = {
        "all_leads": len(leads),
        "unassigned": sum(1 for row in leads if row.get("unassigned")),
        "overdue": sum(1 for row in leads if row.get("overdue_followup")),
        "needs_attention": sum(1 for row in leads if row.get("needs_attention")),
        "retrying": sum(1 for row in leads if row.get("retrying")),
        "failed": sum(1 for row in leads if row.get("pipeline_failed")),
    }
    return {"categories": cards, "management": is_management(), "summary": summary, "generated_at": now_datetime()}


@frappe.whitelist()
def groups(category):
    _require_category(category)
    rows = _permitted_leads({"lead_category": category})
    grouped = {}
    for row in rows:
        label = row.get("lead_group") or "Unspecified"
        item = grouped.setdefault(label, {"name": label, "total": 0, "new": 0, "unassigned": 0, "latest": None})
        item["total"] += 1
        item["new"] += cint(_is_new(row))
        item["unassigned"] += cint(_is_unassigned(row))
        activity_at = row.get("modified") or row.get("creation")
        item["latest"] = max(filter(None, [item["latest"], activity_at]), default=activity_at)
    return {"category": category, "groups": sorted(grouped.values(), key=lambda row: (row["latest"] or now_datetime(), row["name"]), reverse=True)}


@frappe.whitelist()
def leads(category=None, group=None, search=None, start=0, page_length=30, from_date=None, to_date=None, classification_filter=None):
    _require_operational()
    filters = {}
    if category and category not in ("All", "all"):
        if category == "Uncategorized":
            filters["lead_category"] = ["in", ["", "Uncategorized", None]]
        else:
            _require_category(category)
            filters["lead_category"] = category

    if classification_filter:
        if classification_filter == "Categorized":
            filters["lead_category"] = ["not in", ["", "Uncategorized", None]]
        elif classification_filter == "Uncategorized":
            filters["lead_category"] = ["in", ["", "Uncategorized", None]]
        elif classification_filter in ("Manual", "Automatic"):
            filters["classification_source"] = classification_filter

    if group:
        if group in ("Unspecified", "No Subcategory"):
            filters["lead_group"] = ["in", ["", "Unspecified", "No Subcategory", None]]
        else:
            filters["lead_group"] = group

    if from_date:
        filters["creation"] = [">=", getdate(from_date)]
    if to_date:
        filters["creation"] = ["<=", getdate(to_date)]

    fields = [field for field in LEAD_FIELDS if _lead_has_field(field)]
    or_filters = None
    if search:
        term = f"%{str(search).strip()}%"
        searchable = [field for field in ("lead_name", "first_name", "last_name", "mobile_no", "phone", "email", "facebook_lead_id", "meta_campaign_name", "lead_group", "visa_type", "custom_visa_type") if frappe.get_meta("CRM Lead").has_field(field)]
        or_filters = [["CRM Lead", field, "like", term] for field in searchable]

    rows = frappe.get_all("CRM Lead", filters=filters, or_filters=or_filters, fields=fields, order_by="creation desc, name desc", start=max(cint(start), 0), page_length=min(max(cint(page_length), 1), 100))
    _add_operational_flags(rows)
    return {"category": category or "All", "group": group, "rows": rows, "has_more": len(rows) == min(max(cint(page_length), 1), 100)}


@frappe.whitelist()
def classify(lead, category, group=None, reason=None):
    result = apply_manual_classification(lead, category, group=group, reason=reason)
    frappe.db.commit()
    return {"ok": True, "classification": result}


@frappe.whitelist()
def bulk_classify(leads, category, group=None, reason=None):
    _require_operational()
    if isinstance(leads, str):
        import json
        leads = json.loads(leads)
    if not isinstance(leads, list):
        frappe.throw("Invalid leads parameter: must be a list of lead names")

    results = []
    succeeded = []
    failed = []
    for lead_name in leads:
        try:
            res = apply_manual_classification(lead_name, category, group=group, reason=reason)
            succeeded.append({"lead": lead_name, "result": res})
            results.append({"lead": lead_name, "status": "moved"})
        except Exception as exc:
            err_msg = str(exc)
            failed.append({"lead": lead_name, "error": err_msg})
            results.append({"lead": lead_name, "status": "failed", "error": err_msg})

    frappe.db.commit()
    return {
        "ok": len(failed) == 0,
        "success": len(failed) == 0,
        "moved": len(succeeded),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
        "total": len(leads),
    }


@frappe.whitelist()
def subcategories(category=None):
    _require_operational()
    filters = {}
    if category and category not in ("All", "all"):
        if category == "Uncategorized":
            filters["lead_category"] = ["in", ["", "Uncategorized", None]]
        else:
            filters["lead_category"] = category

    groups_list = frappe.get_all("CRM Lead", filters=filters, pluck="lead_group", distinct=True)
    valid_groups = sorted([g for g in groups_list if g and g not in ("Unspecified", "No Subcategory")])

    if frappe.db.exists("DocType", "Lead Subcategory"):
        sub_cat_filters = {"is_active": 1}
        if category and category not in ("All", "all", "Uncategorized"):
            sub_cat_filters["parent_category"] = category
        db_subcats = frappe.get_all("Lead Subcategory", filters=sub_cat_filters, pluck="sub_category_name")
        for sc in db_subcats:
            if sc and sc not in valid_groups:
                valid_groups.append(sc)
        valid_groups = sorted(list(set(valid_groups)))

    categories_list = frappe.get_all(
        "Lead Category",
        filters={"is_active": 1},
        fields=["name", "category_name", "department"],
        order_by="sort_order asc, category_name asc"
    )
    return {
        "category": category,
        "subcategories": valid_groups,
        "categories": categories_list
    }


@frappe.whitelist()
def create_category(category_name, department=None, sort_order=100, operational_status="Active", description=None):
    require_management()
    if frappe.db.exists("Lead Category", category_name):
        frappe.throw("Lead Category already exists", frappe.DuplicateEntryError)
    if department and not frappe.db.exists("Department", department):
        frappe.throw("Department does not exist", frappe.LinkValidationError)
    doc = frappe.get_doc({
        "doctype": "Lead Category",
        "category_name": str(category_name).strip(),
        "department": department,
        "sort_order": cint(sort_order),
        "operational_status": operational_status,
        "is_active": 1,
        "description": description,
    })
    doc.insert(ignore_permissions=True)
    return {"name": doc.name}


@frappe.whitelist()
def create_sub_category(sub_category_name, parent_category, description=None, sort_order=100):
    _require_operational()
    if not parent_category or not frappe.db.exists("Lead Category", parent_category):
        frappe.throw("Valid Parent Lead Category is required", frappe.ValidationError)
    name = str(sub_category_name).strip()
    if not name:
        frappe.throw("Sub-category Name is required", frappe.ValidationError)

    if frappe.db.exists("DocType", "Lead Subcategory"):
        if frappe.db.exists("Lead Subcategory", {"sub_category_name": name, "parent_category": parent_category}):
            frappe.throw(f"Sub-category '{name}' already exists under category '{parent_category}'", frappe.DuplicateEntryError)
        doc = frappe.get_doc({
            "doctype": "Lead Subcategory",
            "sub_category_name": name,
            "parent_category": parent_category,
            "description": description,
            "sort_order": cint(sort_order),
            "is_active": 1,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return {"name": doc.name, "sub_category_name": name, "parent_category": parent_category}
    else:
        return {"name": name, "sub_category_name": name, "parent_category": parent_category}


def _categories():
    names = accessible_categories()
    if not names:
        return []
    rows = frappe.get_all("Lead Category", filters={"name": ["in", names], "is_active": 1}, fields=["name", "category_name", "category_key", "department", "sort_order", "operational_status", "is_uncategorized"], order_by="sort_order asc, category_name asc", page_length=0)
    if not is_management():
        rows = [row for row in rows if row.operational_status == "Active"]
    return rows


def _permitted_leads(filters=None):
    fields = [field for field in LEAD_FIELDS if _lead_has_field(field)]
    filters = dict(filters or {})
    if not is_management():
        categories = accessible_categories()
        if not categories:
            return []
        requested = filters.get("lead_category")
        if isinstance(requested, str) and requested not in categories and requested not in ("Uncategorized", "All"):
            frappe.throw("Not permitted for this lead category", frappe.PermissionError)
        if not requested:
            filters["lead_category"] = ["in", categories]
    return frappe.get_all("CRM Lead", filters=filters, fields=fields, order_by="creation desc", page_length=0)


def _require_operational():
    if frappe.session.user == "Guest" or not is_operational():
        frappe.throw("Visa CRM operational access required", frappe.PermissionError)


def _require_category(category):
    _require_operational()
    if category not in accessible_categories():
        frappe.throw("Not permitted for this lead category", frappe.PermissionError)


def _add_operational_flags(rows):
    names = [row.name for row in rows]
    queues = {}
    if names:
        for queue in frappe.get_all("Lead Intake Queue", filters={"matched_lead": ["in", names]}, fields=["matched_lead", "orchestration_status", "current_stage", "status", "next_action_at"], order_by="creation desc"):
            queues.setdefault(queue.matched_lead, queue)
    overdue = set()
    if names:
        overdue = set(frappe.get_all("ToDo", filters={"reference_type": "CRM Lead", "reference_name": ["in", names], "status": "Open", "date": ["<", getdate()]}, pluck="reference_name"))
    for row in rows:
        queue = queues.get(row.name)
        row.update({
            "is_new": _is_new(row),
            "unassigned": _is_unassigned(row),
            "overdue_followup": row.name in overdue,
            "needs_attention": _needs_attention(row) or row.name in overdue or bool(queue and queue.get("orchestration_status") == "FAILED"),
            "pipeline_status": queue.get("orchestration_status") if queue else None,
            "pipeline_stage": queue.get("current_stage") if queue else None,
            "retrying": bool(queue and queue.get("orchestration_status") in ("RUNNING", "PARTIALLY_COMPLETED")),
            "pipeline_failed": bool(queue and queue.get("orchestration_status") == "FAILED"),
        })


def _is_new(row):
    return str(row.get("status") or "").casefold() in ("new", "lead", "open", "")


def _is_unassigned(row):
    return not (row.get("lead_owner") or row.get("assigned_counselor") or row.get("assigned_employee"))


def _needs_attention(row):
    return str(row.get("status") or "").casefold() in ("needs assignment", "failed", "lost") or row.get("classification_status") == "Needs Review" or bool(row.get("pipeline_failed"))


def _lead_has_field(fieldname):
    return fieldname in STANDARD_DOCUMENT_FIELDS or frappe.get_meta("CRM Lead").has_field(fieldname)
