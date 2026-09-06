"""
Controlled MCP (Model Context Protocol) API for Frappe CRM.
Phase 3: Controlled Read-Only Reporting API Suite.

Architecture:
Google Gemini (External Client) -> MCP Server -> Frappe CRM Whitelisted APIs

Security & Data Integrity Guarantees:
- Explicitly whitelisted endpoints.
- Requires authenticated Frappe session or API Token.
- Enforces Frappe document read permissions.
- No arbitrary SQL execution.
- No arbitrary DocType access.
- No caller-controlled field projection.
- Safe dynamic field resolution against active metadata.
"""

from datetime import datetime
import re
import frappe
from frappe.utils import nowdate


def _check_auth_and_permission(doctype: str):
	if not frappe.session or frappe.session.user == "Guest":
		frappe.throw("Authentication required to access CRM MCP APIs", frappe.PermissionError)
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(f"Insufficient permissions to read {doctype} records", frappe.PermissionError)


def _validate_iso_date(val, field_name, required=False):
	if val is None or (isinstance(val, str) and not val.strip()):
		if required:
			frappe.throw(f"{field_name} is required and cannot be empty.", frappe.ValidationError)
		return None
	val = val.strip()
	if not re.match(r"^\d{4}-\d{2}-\d{2}$", val):
		frappe.throw(
			f"Invalid {field_name} format. Date must be strictly in YYYY-MM-DD format (e.g. 2026-09-06).",
			frappe.ValidationError,
		)
	try:
		datetime.strptime(val, "%Y-%m-%d")
	except ValueError:
		frappe.throw(f"Invalid calendar date for {field_name}. Please provide a valid calendar day.", frappe.ValidationError)
	return val


def _get_lead_fields_meta():
	meta = frappe.get_meta("CRM Lead")
	fields = ["name", "creation"]
	for f in ("lead_name", "first_name", "last_name", "email", "mobile_no", "phone", "status", "source"):
		if meta.has_field(f):
			fields.append(f)

	counselor_field = None
	for f in ("assigned_counselor", "assigned_employee", "lead_owner"):
		if meta.has_field(f):
			counselor_field = f
			if f not in fields:
				fields.append(f)
			break

	dept_field = None
	for f in ("department", "responsible_department"):
		if meta.has_field(f):
			dept_field = f
			if f not in fields:
				fields.append(f)
			break

	return fields, counselor_field, dept_field


def _format_lead_records(records, counselor_field, dept_field):
	leads = []
	for rec in records:
		customer_name = (
			rec.get("lead_name")
			or f"{rec.get('first_name') or ''} {rec.get('last_name') or ''}".strip()
			or rec.get("name")
		)
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
		counselor = rec.get(counselor_field) if counselor_field else None
		if counselor in (None, "", "Administrator", "Guest"):
			counselor = None
		lead_item["assigned_counselor"] = counselor

		lead_item["department"] = rec.get(dept_field) if dept_field else None
		leads.append(lead_item)
	return leads


# =============================================================================
# TOOL 1: get_today_leads (Phase 1, preserved)
# =============================================================================
@frappe.whitelist()
def get_today_leads():
	_check_auth_and_permission("CRM Lead")
	if not frappe.db.exists("DocType", "CRM Lead"):
		return {"success": False, "date": nowdate(), "total": 0, "leads": [], "error": "CRM Lead DocType does not exist"}

	fields_to_fetch, counselor_field, dept_field = _get_lead_fields_meta()
	today_str = nowdate()

	records = frappe.get_list(
		"CRM Lead",
		filters=[
			["CRM Lead", "creation", ">=", f"{today_str} 00:00:00"],
			["CRM Lead", "creation", "<=", f"{today_str} 23:59:59"],
		],
		fields=fields_to_fetch,
		order_by="creation desc",
		limit_page_length=500,
	)
	leads = _format_lead_records(records, counselor_field, dept_field)
	return {"success": True, "date": today_str, "total": len(leads), "leads": leads}


# =============================================================================
# TOOL 2: get_leads_by_date
# =============================================================================
@frappe.whitelist()
def get_leads_by_date(date: str):
	_check_auth_and_permission("CRM Lead")
	valid_date = _validate_iso_date(date, "date", required=True)
	fields_to_fetch, counselor_field, dept_field = _get_lead_fields_meta()

	records = frappe.get_list(
		"CRM Lead",
		filters=[
			["CRM Lead", "creation", ">=", f"{valid_date} 00:00:00"],
			["CRM Lead", "creation", "<=", f"{valid_date} 23:59:59"],
		],
		fields=fields_to_fetch,
		order_by="creation desc",
		limit_page_length=500,
	)
	leads = _format_lead_records(records, counselor_field, dept_field)
	return {"success": True, "date": valid_date, "total": len(leads), "leads": leads}


# =============================================================================
# TOOL 3: get_lead_report
# =============================================================================
@frappe.whitelist()
def get_lead_report(start_date: str, end_date: str):
	_check_auth_and_permission("CRM Lead")
	valid_start = _validate_iso_date(start_date, "start_date", required=True)
	valid_end = _validate_iso_date(end_date, "end_date", required=True)
	if valid_start > valid_end:
		frappe.throw(f"start_date '{valid_start}' cannot be after end_date '{valid_end}'.", frappe.ValidationError)

	fields_to_fetch, counselor_field, dept_field = _get_lead_fields_meta()
	records = frappe.get_list(
		"CRM Lead",
		filters=[
			["CRM Lead", "creation", ">=", f"{valid_start} 00:00:00"],
			["CRM Lead", "creation", "<=", f"{valid_end} 23:59:59"],
		],
		fields=fields_to_fetch,
		order_by="creation desc",
		limit_page_length=500,
	)
	leads = _format_lead_records(records, counselor_field, dept_field)

	by_dept = {}
	by_source = {}
	by_status = {}
	assigned_count = 0
	unassigned_count = 0

	for l in leads:
		d = l.get("department") or "Unspecified"
		by_dept[d] = by_dept.get(d, 0) + 1
		s = l.get("source") or "Unspecified"
		by_source[s] = by_source.get(s, 0) + 1
		st = l.get("status") or "Unspecified"
		by_status[st] = by_status.get(st, 0) + 1
		if l.get("assigned_counselor"):
			assigned_count += 1
		else:
			unassigned_count += 1

	return {
		"success": True,
		"start_date": valid_start,
		"end_date": valid_end,
		"total_leads": len(leads),
		"leads_by_department": by_dept,
		"leads_by_source": by_source,
		"leads_by_status": by_status,
		"assigned_vs_unassigned": {"assigned": assigned_count, "unassigned": unassigned_count},
		"leads": leads,
	}


# =============================================================================
# TOOL 4: get_leads_by_department
# =============================================================================
@frappe.whitelist()
def get_leads_by_department(department: str):
	_check_auth_and_permission("CRM Lead")
	if not department or not department.strip():
		frappe.throw("department parameter cannot be empty.", frappe.ValidationError)
	dept_query = department.strip()

	fields_to_fetch, counselor_field, dept_field = _get_lead_fields_meta()
	target_dept_field = dept_field or "responsible_department"

	records = frappe.get_list(
		"CRM Lead",
		filters=[["CRM Lead", target_dept_field, "like", f"%{dept_query}%"]],
		fields=fields_to_fetch,
		order_by="creation desc",
		limit_page_length=500,
	)
	leads = _format_lead_records(records, counselor_field, dept_field)
	return {"success": True, "department": dept_query, "total": len(leads), "leads": leads}


# =============================================================================
# TOOL 5: get_leads_by_counselor
# =============================================================================
@frappe.whitelist()
def get_leads_by_counselor(counselor: str):
	_check_auth_and_permission("CRM Lead")
	if not counselor or not counselor.strip():
		frappe.throw("counselor parameter cannot be empty.", frappe.ValidationError)
	counselor_query = counselor.strip()

	fields_to_fetch, counselor_field, dept_field = _get_lead_fields_meta()
	target_counselor_field = counselor_field or "lead_owner"

	records = frappe.get_list(
		"CRM Lead",
		filters=[["CRM Lead", target_counselor_field, "like", f"%{counselor_query}%"]],
		fields=fields_to_fetch,
		order_by="creation desc",
		limit_page_length=500,
	)
	leads = _format_lead_records(records, counselor_field, dept_field)
	return {"success": True, "counselor": counselor_query, "total": len(leads), "leads": leads}


# =============================================================================
# TOOL 6: get_lead_sources
# =============================================================================
@frappe.whitelist()
def get_lead_sources(start_date: str = None, end_date: str = None):
	_check_auth_and_permission("CRM Lead")
	valid_start = _validate_iso_date(start_date, "start_date")
	valid_end = _validate_iso_date(end_date, "end_date")
	if valid_start and valid_end and valid_start > valid_end:
		frappe.throw(f"start_date '{valid_start}' cannot be after end_date '{valid_end}'.", frappe.ValidationError)

	filters = []
	if valid_start:
		filters.append(["CRM Lead", "creation", ">=", f"{valid_start} 00:00:00"])
	if valid_end:
		filters.append(["CRM Lead", "creation", "<=", f"{valid_end} 23:59:59"])

	records = frappe.get_list("CRM Lead", filters=filters, fields=["name", "source"], limit_page_length=500)
	sources = {}
	for r in records:
		s = r.get("source") or "Unspecified"
		sources[s] = sources.get(s, 0) + 1

	return {"success": True, "start_date": valid_start, "end_date": valid_end, "total": len(records), "sources": sources}


# =============================================================================
# TOOL 7: get_unassigned_leads
# =============================================================================
@frappe.whitelist()
def get_unassigned_leads(start_date: str = None, end_date: str = None):
	_check_auth_and_permission("CRM Lead")
	valid_start = _validate_iso_date(start_date, "start_date")
	valid_end = _validate_iso_date(end_date, "end_date")
	if valid_start and valid_end and valid_start > valid_end:
		frappe.throw(f"start_date '{valid_start}' cannot be after end_date '{valid_end}'.", frappe.ValidationError)

	filters = []
	if valid_start:
		filters.append(["CRM Lead", "creation", ">=", f"{valid_start} 00:00:00"])
	if valid_end:
		filters.append(["CRM Lead", "creation", "<=", f"{valid_end} 23:59:59"])

	fields_to_fetch, counselor_field, dept_field = _get_lead_fields_meta()
	meta = frappe.get_meta("CRM Lead")
	if meta.has_field("assignment_status") and "assignment_status" not in fields_to_fetch:
		fields_to_fetch.append("assignment_status")

	records = frappe.get_list("CRM Lead", filters=filters, fields=fields_to_fetch, order_by="creation desc", limit_page_length=500)
	all_leads = _format_lead_records(records, counselor_field, dept_field)

	unassigned = []
	for idx, r in enumerate(records):
		owner = r.get(counselor_field) if counselor_field else None
		status = r.get("assignment_status")
		if status in ("Unassigned", "Needs Assignment") or owner in (None, "", "Administrator", "Guest"):
			unassigned.append(all_leads[idx])

	return {"success": True, "start_date": valid_start, "end_date": valid_end, "total": len(unassigned), "unassigned_leads": unassigned}


# =============================================================================
# TOOL 8: get_followups
# =============================================================================
@frappe.whitelist()
def get_followups(start_date: str = None, end_date: str = None):
	_check_auth_and_permission("ToDo")
	valid_start = _validate_iso_date(start_date, "start_date")
	valid_end = _validate_iso_date(end_date, "end_date")
	if valid_start and valid_end and valid_start > valid_end:
		frappe.throw(f"start_date '{valid_start}' cannot be after end_date '{valid_end}'.", frappe.ValidationError)

	filters = []
	if valid_start:
		filters.append(["ToDo", "creation", ">=", f"{valid_start} 00:00:00"])
	if valid_end:
		filters.append(["ToDo", "creation", "<=", f"{valid_end} 23:59:59"])

	records = frappe.get_list(
		"ToDo",
		filters=filters,
		fields=["name", "description", "status", "priority", "date", "allocated_to", "reference_type", "reference_name", "creation"],
		order_by="creation desc",
		limit_page_length=500,
	)
	followups = []
	for t in records:
		desc = t.get("description") or ""
		ref = t.get("reference_type")
		if ref in ("CRM Lead", "Lead Intake Queue") or "follow" in desc.lower():
			followups.append({
				"name": t.get("name"),
				"description": desc,
				"due_date": str(t.get("date")) if t.get("date") else None,
				"status": t.get("status"),
				"assigned_to": t.get("allocated_to"),
				"linked_crm_record": t.get("reference_name"),
				"priority": t.get("priority"),
				"creation": str(t.get("creation")),
			})

	return {"success": True, "start_date": valid_start, "end_date": valid_end, "total": len(followups), "followups": followups}


# =============================================================================
# TOOL 9: get_tasks
# =============================================================================
@frappe.whitelist()
def get_tasks(start_date: str = None, end_date: str = None, assigned_employee: str = None):
	_check_auth_and_permission("ToDo")
	valid_start = _validate_iso_date(start_date, "start_date")
	valid_end = _validate_iso_date(end_date, "end_date")
	if valid_start and valid_end and valid_start > valid_end:
		frappe.throw(f"start_date '{valid_start}' cannot be after end_date '{valid_end}'.", frappe.ValidationError)

	filters = []
	if valid_start:
		filters.append(["ToDo", "creation", ">=", f"{valid_start} 00:00:00"])
	if valid_end:
		filters.append(["ToDo", "creation", "<=", f"{valid_end} 23:59:59"])
	if assigned_employee and assigned_employee.strip():
		filters.append(["ToDo", "allocated_to", "like", f"%{assigned_employee.strip()}%"])

	records = frappe.get_list(
		"ToDo",
		filters=filters,
		fields=["name", "description", "status", "priority", "date", "allocated_to", "reference_type", "reference_name", "creation"],
		order_by="creation desc",
		limit_page_length=500,
	)
	tasks = []
	for t in records:
		tasks.append({
			"task_name": t.get("name"),
			"subject": t.get("description"),
			"assigned_employee": t.get("allocated_to"),
			"due_date": str(t.get("date")) if t.get("date") else None,
			"status": t.get("status"),
			"linked_crm_record": t.get("reference_name"),
			"priority": t.get("priority"),
		})

	return {"success": True, "start_date": valid_start, "end_date": valid_end, "assigned_employee": assigned_employee, "total": len(tasks), "tasks": tasks}


# =============================================================================
# TOOL 10: get_visa_applications
# =============================================================================
@frappe.whitelist()
def get_visa_applications(start_date: str = None, end_date: str = None, status: str = None):
	_check_auth_and_permission("Visa Application")
	valid_start = _validate_iso_date(start_date, "start_date")
	valid_end = _validate_iso_date(end_date, "end_date")
	if valid_start and valid_end and valid_start > valid_end:
		frappe.throw(f"start_date '{valid_start}' cannot be after end_date '{valid_end}'.", frappe.ValidationError)

	filters = []
	if valid_start:
		filters.append(["Visa Application", "creation", ">=", f"{valid_start} 00:00:00"])
	if valid_end:
		filters.append(["Visa Application", "creation", "<=", f"{valid_end} 23:59:59"])
	if status and status.strip():
		filters.append(["Visa Application", "status", "=", status.strip()])

	records = frappe.get_list(
		"Visa Application",
		filters=filters,
		fields=["name", "applicant_name", "customer", "lead", "visa_type", "country", "status", "submitted_on", "decision_on", "creation"],
		order_by="creation desc",
		limit_page_length=500,
	)
	visas = []
	for v in records:
		visas.append({
			"name": v.get("name"),
			"applicant_name": v.get("applicant_name"),
			"customer": v.get("customer"),
			"lead": v.get("lead"),
			"visa_type": v.get("visa_type"),
			"country": v.get("country"),
			"status": v.get("status"),
			"submitted_on": str(v.get("submitted_on")) if v.get("submitted_on") else None,
			"decision_on": str(v.get("decision_on")) if v.get("decision_on") else None,
			"creation": str(v.get("creation")),
		})

	return {"success": True, "start_date": valid_start, "end_date": valid_end, "status": status, "total": len(visas), "visa_applications": visas}

# =============================================================================
# TOOL 11: get_management_summary
# =============================================================================
@frappe.whitelist()
@frappe.whitelist()
def get_management_summary(date=None):
	"""Returns an aggregated executive CRM summary across leads, assignments, follow-ups, and visas."""
	target_date = date or today()

	# 1. Leads
	leads = frappe.get_list(
		"CRM Lead",
		filters=[
			["CRM Lead", "creation", ">=", f"{target_date} 00:00:00"],
			["CRM Lead", "creation", "<=", f"{target_date} 23:59:59"],
		],
		fields=["name", "lead_name", "status", "source", "responsible_department", "assigned_counselor", "lead_owner", "creation"],
		limit_page_length=500,
	)

	dept_counts = {}
	source_counts = {}
	status_counts = {}
	counselor_counts = {}
	for l in leads:
		d = l.get("responsible_department") or "Unspecified"
		dept_counts[d] = dept_counts.get(d, 0) + 1
		s = l.get("source") or "Unspecified"
		source_counts[s] = source_counts.get(s, 0) + 1
		st = l.get("status") or "Unspecified"
		status_counts[st] = status_counts.get(st, 0) + 1
		owner = l.get("assigned_counselor") or l.get("lead_owner")
		if owner:
			counselor_counts[owner] = counselor_counts.get(owner, 0) + 1

	# 2. Assignment
	unassigned = [l for l in leads if not (l.get("assigned_counselor") or l.get("lead_owner"))]
	assigned_count = len(leads) - len(unassigned)
	backlog_rate = f"{(len(unassigned) / len(leads) * 100):.1f}%" if leads else "0.0%"

	# 3. Followups
	followups_raw = frappe.get_list(
		"ToDo",
		filters=[
			["ToDo", "creation", ">=", f"{target_date} 00:00:00"],
			["ToDo", "creation", "<=", f"{target_date} 23:59:59"],
		],
		fields=["name", "description", "status", "priority", "date", "allocated_to", "reference_type", "reference_name"],
		limit_page_length=500,
	)
	open_followups = [t for t in followups_raw if t.get("status") == "Open"]
	overdue_followups = [t for t in open_followups if t.get("date") and str(t.get("date")) < target_date]

	# 4. Visa Applications
	month_start = f"{target_date[:7]}-01"
	visas_raw = frappe.get_list(
		"Visa Application",
		filters=[
			["Visa Application", "creation", ">=", f"{month_start} 00:00:00"],
			["Visa Application", "creation", "<=", f"{target_date} 23:59:59"],
		],
		fields=["name", "applicant_name", "status", "creation"],
		limit_page_length=500,
	)
	visa_status_counts = {}
	for v in visas_raw:
		st = v.get("status") or "Unspecified"
		visa_status_counts[st] = visa_status_counts.get(st, 0) + 1

	attention = []
	if unassigned:
		attention.append(f"{len(unassigned)} lead(s) on {target_date} need counselor assignment ({backlog_rate} unassigned backlog).")
	if overdue_followups:
		attention.append(f"{len(overdue_followups)} overdue follow-up task(s) require counselor attention.")
	if open_followups:
		attention.append(f"{len(open_followups)} open follow-up task(s) active on {target_date}.")

	return {
		"success": True,
		"date": target_date,
		"summary_title": f"Executive CRM Management Summary for {target_date}",
		"leads": {
			"total": len(leads),
			"by_department": dept_counts,
			"by_source": source_counts,
			"by_status": status_counts,
		},
		"assignment": {
			"assigned": assigned_count,
			"unassigned": len(unassigned),
			"backlog_rate": backlog_rate,
			"counselor_distribution": counselor_counts,
			"unassigned_lead_ids": [l["name"] for l in unassigned[:10]],
		},
		"followups": {
			"total": len(followups_raw),
			"open_count": len(open_followups),
			"overdue_count": len(overdue_followups),
			"backlog": len(open_followups),
			"sample": followups_raw[:5],
		},
		"visa_applications": {
			"month_to_date_total": len(visas_raw),
			"by_status": visa_status_counts,
			"sample": visas_raw[:5],
		},
		"attention_required": attention,
	}
