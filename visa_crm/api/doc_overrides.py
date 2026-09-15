# Copyright (c) 2026, Shahbaz and contributors
# For license information, please see license.txt

import json
import frappe
from frappe import _
from crm.api.doc import get_data as base_get_data
from visa_crm.overrides.contact import VisaCRMContact


@frappe.whitelist()
def get_data(
	doctype: str,
	filters: dict | str = None,
	order_by: str = None,
	page_length: int = 20,
	page_length_count: int = 20,
	column_field: str | None = None,
	title_field: str | None = None,
	columns: str | list | None = None,
	rows: str | list | None = None,
	kanban_columns: str | list | None = None,
	kanban_fields: str | list | None = None,
	view: str | dict | None = None,
	default_filters: dict | str | None = None,
):
	"""
	Custom wrapper around crm.api.doc.get_data:
	1. Normalizes Lead filters (category -> lead_category, subcategory -> lead_group, Like queries).
	2. Sanitizes query rows and enriches virtual columns (Contacts: customer_name, category, subcat).
	3. Enriches CRM Deal list view with rich staff-friendly columns and batch lead fallback.
	4. Ensures all sidebar lists and Tree view filters work seamlessly.
	"""
	if isinstance(filters, str):
		try:
			filters = json.loads(filters)
		except Exception:
			filters = {}
	elif filters is None:
		filters = {}

	if isinstance(default_filters, str):
		try:
			default_filters = json.loads(default_filters)
		except Exception:
			default_filters = {}

	if doctype == "CRM Lead":
		if isinstance(filters, dict):
			filters = normalize_crm_lead_filters(filters)
		if isinstance(default_filters, dict):
			default_filters = normalize_crm_lead_filters(default_filters)

	# For CRM Deal, ensure 14 rich columns are supplied if not customized
	if doctype == "CRM Deal":
		view_type = "list"
		if isinstance(view, str):
			try:
				view_dict = json.loads(view)
				view_type = view_dict.get("view_type") or "list"
			except Exception:
				view_type = "list"
		elif isinstance(view, dict):
			view_type = view.get("view_type") or "list"

		if view_type == "list" and not columns:
			from visa_crm.overrides.deal import VisaCRMDeal
			default_data = VisaCRMDeal.default_list_data()
			columns = default_data["columns"]
			if not rows:
				rows = default_data["rows"]

	# For Contact, sanitize custom columns so MySQL get_list doesn't fail
	if doctype == "Contact":
		if isinstance(rows, str):
			try:
				rows = json.loads(rows)
			except Exception:
				rows = []
		if isinstance(rows, list):
			virtual_fields = {"customer_name", "lead_category", "lead_group"}
			rows = [r for r in rows if r not in virtual_fields]

	# Execute base get_data
	res = base_get_data(
		doctype=doctype,
		filters=filters,
		order_by=order_by,
		page_length=page_length,
		page_length_count=page_length_count,
		column_field=column_field,
		title_field=title_field,
		columns=columns,
		rows=rows,
		kanban_columns=kanban_columns,
		kanban_fields=kanban_fields,
		view=view,
		default_filters=default_filters,
	)

	# Ensure Contact list has dynamic columns enriched
	if doctype == "Contact" and isinstance(res, dict) and "data" in res:
		res["data"] = VisaCRMContact.parse_list_data(res["data"])

	# Ensure CRM Deal list gracefully enriches missing lead fields in batch
	if doctype == "CRM Deal" and isinstance(res, dict) and "data" in res:
		res["data"] = enrich_deal_list_data(res["data"])

	return res


def enrich_deal_list_data(deal_rows: list) -> list:
	"""Batch enrich empty deal fields from linked CRM Lead without N+1 queries."""
	if not deal_rows:
		return deal_rows

	leads_to_fetch = set()
	for row in deal_rows:
		if isinstance(row, dict) and row.get("lead"):
			if not row.get("email") or not row.get("mobile_no") or not row.get("lead_name"):
				leads_to_fetch.add(row["lead"])

	if not leads_to_fetch:
		return deal_rows

	lead_records = frappe.get_all(
		"CRM Lead",
		filters={"name": ["in", list(leads_to_fetch)]},
		fields=[
			"name", "lead_name", "first_name", "last_name", "email", "mobile_no", "phone",
			"meta_campaign_name", "meta_adset_name", "lead_category", "responsible_department",
			"custom_destination"
		],
	)
	lead_map = {l.name: l for l in lead_records}

	for row in deal_rows:
		if isinstance(row, dict) and row.get("lead") in lead_map:
			lead_info = lead_map[row["lead"]]
			if not row.get("lead_name"):
				row["lead_name"] = lead_info.lead_name or f"{lead_info.first_name or ''} {lead_info.last_name or ''}".strip()
			if not row.get("email"):
				row["email"] = lead_info.email
			if not row.get("mobile_no"):
				row["mobile_no"] = lead_info.mobile_no
			if not row.get("phone"):
				row["phone"] = lead_info.phone or lead_info.mobile_no
			if not row.get("custom_meta_campaign_name"):
				row["custom_meta_campaign_name"] = getattr(lead_info, "meta_campaign_name", None)
			if not row.get("custom_meta_adset_name"):
				row["custom_meta_adset_name"] = getattr(lead_info, "meta_adset_name", None)
			if not row.get("custom_lead_category"):
				row["custom_lead_category"] = getattr(lead_info, "lead_category", None)
			if not row.get("custom_responsible_department"):
				row["custom_responsible_department"] = getattr(lead_info, "responsible_department", None)
			if not row.get("custom_destination"):
				row["custom_destination"] = getattr(lead_info, "custom_destination", None)

	return deal_rows


def normalize_crm_lead_filters(filters: dict) -> dict:
	"""
	Normalize search and URL query filters on CRM Lead:
	- category -> lead_category
	- subcategory -> lead_group
	- LIKE / = on name or lead_name -> search across name, lead_name, first_name, last_name, organization
	"""
	if not filters or not isinstance(filters, dict):
		return filters or {}

	new_filters = dict(filters)

	# Map URL param 'category' to 'lead_category'
	if "category" in new_filters:
		val = new_filters.pop("category")
		if val and val != "All":
			new_filters["lead_category"] = val

	# Map URL param 'subcategory' to 'lead_group'
	if "subcategory" in new_filters:
		val = new_filters.pop("subcategory")
		if val and val != "All":
			new_filters["lead_group"] = val

	# Normalize search on name or lead_name
	for target_field in ["name", "lead_name"]:
		if target_field not in new_filters:
			continue

		val = new_filters[target_field]
		operator = "="
		search_term = ""

		if isinstance(val, (list, tuple)) and len(val) >= 2:
			operator = str(val[0]).lower()
			search_term = str(val[1])
		elif isinstance(val, str):
			search_term = val

		if not search_term:
			continue

		# If searching on 'name' and it's already an exact series ID (e.g. CRM-LEAD-2026-00001)
		if target_field == "name" and operator in ("=", "equals") and search_term.startswith("CRM-LEAD-"):
			continue

		# Format search wildcard pattern
		if "like" in operator:
			pattern = search_term if "%" in search_term else f"%{search_term}%"
		else:
			pattern = f"%{search_term}%"

		matching_leads = frappe.db.sql_list("""
			SELECT name FROM `tabCRM Lead`
			WHERE name LIKE %(pat)s
			   OR lead_name LIKE %(pat)s
			   OR first_name LIKE %(pat)s
			   OR last_name LIKE %(pat)s
			   OR organization LIKE %(pat)s
		""", {"pat": pattern})

		del new_filters[target_field]
		new_filters["name"] = ["in", matching_leads or ["__no_match__"]]
		break

	return new_filters
