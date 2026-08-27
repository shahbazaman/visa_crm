# Copyright (c) 2026, Shahbaz and contributors
# For license information, please see license.txt

import json
import frappe
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
	1. Normalizes LIKE and name filters on CRM Lead to match across lead name, ID, and org.
	2. Sanitizes rows for Contact and enriches dynamic columns (customer_name, category, subcategory).
	"""
	if isinstance(filters, str):
		try:
			filters = json.loads(filters)
		except Exception:
			filters = {}
	elif filters is None:
		filters = {}

	if doctype == "CRM Lead" and isinstance(filters, dict):
		filters = normalize_crm_lead_filters(filters)

	# If querying Contact, remove virtual fields from rows before calling base_get_data
	if doctype == "Contact":
		if isinstance(rows, str):
			try:
				rows = json.loads(rows)
			except Exception:
				rows = []
		if isinstance(rows, list):
			virtual_fields = {"customer_name", "lead_category", "lead_group"}
			rows = [r for r in rows if r not in virtual_fields]

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

	# Ensure Contact list is enriched
	if doctype == "Contact" and isinstance(res, dict) and "data" in res:
		res["data"] = VisaCRMContact.parse_list_data(res["data"])

	return res


def normalize_crm_lead_filters(filters: dict) -> dict:
	"""
	Normalize search queries on CRM Lead:
	If searching by 'name' or 'lead_name' with 'like', 'LIKE', '=', or 'equals':
	Finds all matching lead IDs across name, lead_name, first_name, last_name, and organization.
	"""
	new_filters = dict(filters)

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

		# If searching on 'name' and it already looks like exact series ID (e.g. CRM-LEAD-2026-00001)
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
