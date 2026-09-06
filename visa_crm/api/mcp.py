"""
Controlled MCP (Model Context Protocol) API for Frappe CRM.
Phase 1: Controlled Read API for Today's Leads.

Architecture:
Google Gemini (External Client) -> MCP Server -> Frappe CRM Whitelisted API

Security & Data Integrity Guarantees:
- Explicitly whitelisted endpoint.
- Requires authenticated Frappe session or API Token.
- Enforces Frappe document read permissions on 'CRM Lead'.
- No arbitrary SQL execution.
- No arbitrary DocType access.
- No exposure of credentials, tokens, or private system keys.
- Safe dynamic field resolution against active CRM Lead metadata.
"""

import frappe
from frappe.utils import nowdate


@frappe.whitelist()
def get_today_leads():
	"""
	Controlled MCP endpoint: retrieves CRM Leads created today.

	Returns structured JSON:
	{
	    "success": True,
	    "date": "YYYY-MM-DD",
	    "total": int,
	    "leads": [
	        {
	            "name": str,
	            "customer_name": str,
	            "email": str or None,
	            "phone": str or None,
	            "status": str or None,
	            "source": str or None,
	            "department": str or None,
	            "assigned_counselor": str or None,
	            "creation": str
	        },
	        ...
	    ]
	}
	"""
	# 1. Authentication Check
	if not frappe.session or frappe.session.user == "Guest":
		frappe.throw("Authentication required to access CRM MCP APIs", frappe.PermissionError)

	# 2. Permission Check
	if not frappe.has_permission("CRM Lead", "read"):
		frappe.throw("Insufficient permissions to read CRM Lead records", frappe.PermissionError)

	if not frappe.db.exists("DocType", "CRM Lead"):
		return {
			"success": False,
			"date": nowdate(),
			"total": 0,
			"leads": [],
			"error": "CRM Lead DocType does not exist",
		}

	# 3. Dynamic Field Resolution against active CRM Lead metadata
	meta = frappe.get_meta("CRM Lead")

	fields_to_fetch = ["name", "creation"]

	field_candidates = [
		"lead_name",
		"first_name",
		"last_name",
		"email",
		"mobile_no",
		"phone",
		"status",
		"source",
	]

	for f in field_candidates:
		if meta.has_field(f):
			fields_to_fetch.append(f)

	# Resolve counselor field
	counselor_field = None
	for f in ("assigned_counselor", "assigned_employee", "lead_owner"):
		if meta.has_field(f):
			counselor_field = f
			if f not in fields_to_fetch:
				fields_to_fetch.append(f)
			break

	# Resolve department field
	dept_field = None
	for f in ("department", "responsible_department"):
		if meta.has_field(f):
			dept_field = f
			if f not in fields_to_fetch:
				fields_to_fetch.append(f)
			break

	# 4. Filter records created today using Frappe database APIs
	today_str = nowdate()
	start_time = f"{today_str} 00:00:00"
	end_time = f"{today_str} 23:59:59"

	records = frappe.get_list(
		"CRM Lead",
		filters=[
			["CRM Lead", "creation", ">=", start_time],
			["CRM Lead", "creation", "<=", end_time],
		],
		fields=fields_to_fetch,
		order_by="creation desc",
		limit_page_length=500,
	)

	# 5. Format into clean, structured business schema
	leads = []
	for rec in records:
		# Resolve customer name
		customer_name = (
			rec.get("lead_name")
			or f"{rec.get('first_name') or ''} {rec.get('last_name') or ''}".strip()
			or rec.get("name")
		)

		# Resolve phone number
		phone = rec.get("mobile_no") or rec.get("phone") or None

		lead_item = {
			"name": rec.get("name"),
			"customer_name": customer_name,
			"email": rec.get("email") or None,
			"phone": phone,
			"status": rec.get("status") or None,
			"source": rec.get("source") or None,
			"creation": str(rec.get("creation")),
		}

		if counselor_field:
			lead_item["assigned_counselor"] = rec.get(counselor_field) or None

		if dept_field:
			lead_item["department"] = rec.get(dept_field) or None

		leads.append(lead_item)

	return {
		"success": True,
		"date": today_str,
		"total": len(leads),
		"leads": leads,
	}
