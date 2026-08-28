# Copyright (c) 2026, Shahbaz and contributors
# For license information, please see license.txt

import re
import frappe
from frappe import _
from visa_crm.api.lead_permissions import is_management, is_operational

ALLOWED_WHATSAPP_ROLES = {
	"System Manager",
	"Administrator",
	"Sales Manager",
	"Sales User",
	"Counselor",
	"CRM Manager",
	"HR Manager",
	"HR User",
	"General Manager",
	"Managing Director",
	"MD",
	"Lead Team",
	"Inbox User",
}


def normalize_phone_number(phone: str) -> str:
	"""
	Deterministically normalize a phone number into canonical E.164 / cleaned format.
	Safely handles:
	- '+971 50 123 4567' -> '+971501234567'
	- '0501234567' -> '+971501234567' (UAE domestic)
	- '971501234567' -> '+971501234567'
	- '+91 98379 09369' -> '+919837909369'
	- '09837909369' -> '+919837909369' (India domestic 10-digit)
	- '919837909369' -> '+919837909369'
	"""
	if not phone:
		return ""

	raw = str(phone).strip()
	# Remove spaces, hyphens, brackets, dots
	cleaned = re.sub(r"[\s\-\(\)\.]+", "", raw)

	if not cleaned:
		return ""

	# Handle 00 prefix (international standard for +)
	if cleaned.startswith("00"):
		cleaned = "+" + cleaned[2:]

	if cleaned.startswith("+"):
		return cleaned

	digits = re.sub(r"\D", "", cleaned)
	if not digits:
		return ""

	# UAE domestic number starting with 05 (9 digits total after 0: e.g. 0501234567)
	if digits.startswith("05") and len(digits) == 10:
		return "+971" + digits[1:]

	# UAE international number starting with 971
	if digits.startswith("971") and len(digits) in (12, 13):
		return "+" + digits

	# India domestic number starting with 0 followed by 10 digits
	if digits.startswith("0") and len(digits) == 11 and digits[1] in "6789":
		return "+91" + digits[1:]

	# India international number starting with 91 (12 digits)
	if digits.startswith("91") and len(digits) == 12 and digits[2] in "6789":
		return "+" + digits

	# Standard 10-digit Indian mobile number
	if len(digits) == 10 and digits[0] in "6789":
		return "+91" + digits

	# Default fallback: add + if it looks like international number
	if len(digits) >= 9:
		return "+" + digits

	return digits


def get_phone_search_variants(phone: str) -> list[str]:
	"""
	Return list of possible formatting variants for matching in the database.
	"""
	if not phone:
		return []

	raw = str(phone).strip()
	normalized = normalize_phone_number(raw)
	digits_only = re.sub(r"\D", "", raw)

	variants = {raw, normalized, digits_only}

	# Trailing 9 digits (local core number)
	if len(digits_only) >= 9:
		variants.add(digits_only[-9:])
		variants.add(digits_only[-10:])

	# Without leading +
	if normalized.startswith("+"):
		variants.add(normalized[1:])

	# UAE local with 05
	if normalized.startswith("+971"):
		uae_local = "0" + normalized[4:]
		variants.add(uae_local)

	# India local with 0
	if normalized.startswith("+91"):
		india_local = "0" + normalized[3:]
		variants.add(india_local)
		variants.add(normalized[3:])

	return [v for v in variants if v]


def find_matching_crm_lead(phone: str) -> str | None:
	"""
	Find existing CRM Lead matching the given phone number.
	Never creates a duplicate CRM Lead.
	"""
	if not phone:
		return None

	variants = get_phone_search_variants(phone)
	if not variants:
		return None

	# Search CRM Lead by exact match on mobile_no or phone
	lead_names = frappe.db.sql("""
		SELECT name FROM `tabCRM Lead`
		WHERE mobile_no IN %(variants)s
		   OR phone IN %(variants)s
		ORDER BY modified DESC
		LIMIT 1
	""", {"variants": variants}, pluck="name")

	if lead_names:
		return lead_names[0]

	# Suffix search for 9-digit matching
	core_digits = re.sub(r"\D", "", phone)
	if len(core_digits) >= 9:
		suffix = core_digits[-9:]
		lead_names = frappe.db.sql("""
			SELECT name FROM `tabCRM Lead`
			WHERE (mobile_no LIKE %(pat)s OR phone LIKE %(pat)s)
			ORDER BY modified DESC
			LIMIT 1
		""", {"pat": f"%{suffix}"}, pluck="name")
		if lead_names:
			return lead_names[0]

	return None


def find_matching_customer(phone: str) -> str | None:
	"""
	Find existing Customer matching the given phone number.
	Never creates a duplicate Customer.
	"""
	if not phone:
		return None

	variants = get_phone_search_variants(phone)
	if not variants:
		return None

	customer_names = frappe.db.sql("""
		SELECT name FROM `tabCustomer`
		WHERE mobile_no IN %(variants)s
		   OR ifnull(whatsapp_no, '') IN %(variants)s
		ORDER BY modified DESC
		LIMIT 1
	""", {"variants": variants}, pluck="name")

	if customer_names:
		return customer_names[0]

	core_digits = re.sub(r"\D", "", phone)
	if len(core_digits) >= 9:
		suffix = core_digits[-9:]
		customer_names = frappe.db.sql("""
			SELECT name FROM `tabCustomer`
			WHERE (mobile_no LIKE %(pat)s OR whatsapp_no LIKE %(pat)s)
			ORDER BY modified DESC
			LIMIT 1
		""", {"pat": f"%{suffix}"}, pluck="name")
		if customer_names:
			return customer_names[0]

	return None


def whatsapp_access_guard():
	"""
	Hook called by official frappe/whatsapp run_access_guards().
	Enforces role access according to CRM permission hierarchy.
	"""
	user = frappe.session.user
	if user == "Administrator" or is_management(user) or is_operational(user):
		return

	roles = set(frappe.get_roles(user))
	if not (ALLOWED_WHATSAPP_ROLES & roles):
		frappe.throw(_("You are not permitted to access WhatsApp features."), frappe.PermissionError)


def validate_access(reference_doctype=None, reference_name=None, permtype="read"):
	"""
	Custom access validator for CRM WhatsApp API endpoints.
	Ensures counselors can access WhatsApp for leads they are permitted to view.
	"""
	whatsapp_access_guard()

	if reference_doctype and reference_name:
		if not frappe.db.exists(reference_doctype, reference_name):
			frappe.throw(
				_("Reference document {0} {1} does not exist.").format(reference_doctype, reference_name),
				frappe.DoesNotExistError,
			)
		doc = frappe.get_doc(reference_doctype, reference_name)
		user = frappe.session.user
		if not is_management(user) and not doc.has_permission(permtype):
			frappe.throw(
				_("Not permitted to access reference document {0} {1}.").format(reference_doctype, reference_name),
				frappe.PermissionError,
			)
		return doc

	return None


def on_whatsapp_message_validate(doc, method=None):
	"""
	Hook for WhatsApp Message validate:
	1. Resolve phone number from message (from or to).
	2. Link to CRM Lead or Customer if not already set.
	3. Prevent duplicate incoming messages using message_id idempotency.
	"""
	# Deduplicate incoming webhook messages
	if getattr(doc, "direction", "") == "Incoming" or getattr(doc, "type", "") == "Incoming":
		if doc.message_id and not doc.is_new():
			return

	# If reference is already set, do not override
	if doc.reference_doctype and doc.reference_docname:
		return

	# Extract phone number
	phone_val = ""
	is_incoming = (getattr(doc, "direction", "") == "Incoming" or getattr(doc, "type", "") == "Incoming")
	if is_incoming:
		phone_val = doc.get("from") or ""
	else:
		phone_val = doc.get("to") or ""

	# If 'to' is a WhatsApp Profile name, fetch phone_number from profile
	if phone_val and frappe.db.exists("DocType", "WhatsApp Profile") and frappe.db.exists("WhatsApp Profile", phone_val):
		phone_val = frappe.db.get_value("WhatsApp Profile", phone_val, "phone_number") or phone_val

	if not phone_val:
		return

	# Find matching CRM Lead
	matched_lead = find_matching_crm_lead(phone_val)
	if matched_lead:
		doc.reference_doctype = "CRM Lead"
		doc.reference_docname = matched_lead
		return

	# Find matching Customer
	matched_customer = find_matching_customer(phone_val)
	if matched_customer:
		doc.reference_doctype = "Customer"
		doc.reference_docname = matched_customer


def on_whatsapp_message_after_insert(doc, method=None):
	"""
	Hook for WhatsApp Message after_insert:
	1. Publish realtime event to the active CRM conversation view.
	2. Send CRM Notification to the assigned counselor for incoming messages.
	"""
	if not doc.reference_doctype or not doc.reference_docname:
		return

	# Publish realtime update to CRM Lead Vue SPA
	frappe.publish_realtime(
		"whatsapp_message",
		{
			"reference_doctype": doc.reference_doctype,
			"reference_name": doc.reference_docname,
			"message_id": doc.get("message_id"),
			"name": doc.name,
		},
	)

	is_incoming = (getattr(doc, "direction", "") == "Incoming" or getattr(doc, "type", "") == "Incoming")
	if not is_incoming:
		return

	# Notify assigned counselor if this message is for a CRM Lead
	if doc.reference_doctype == "CRM Lead":
		lead_info = frappe.db.get_value(
			"CRM Lead",
			doc.reference_docname,
			["lead_owner", "assigned_employee", "lead_name", "mobile_no"],
			as_dict=True,
		)
		if not lead_info:
			return

		assigned_user = lead_info.get("lead_owner")
		# If assigned_employee exists and lead_owner is Administrator, check employee user_id
		if lead_info.get("assigned_employee") and (not assigned_user or assigned_user == "Administrator"):
			emp_user = frappe.db.get_value("Employee", lead_info.get("assigned_employee"), "user_id")
			if emp_user:
				assigned_user = emp_user

		if assigned_user and assigned_user != "Administrator" and frappe.db.exists("DocType", "CRM Notification"):
			cust_label = lead_info.get("lead_name") or lead_info.get("mobile_no") or doc.reference_docname
			msg_preview = str(doc.get("message") or doc.get("attach") or "Media Message")
			if len(msg_preview) > 60:
				msg_preview = msg_preview[:57] + "..."

			notif = frappe.new_doc("CRM Notification")
			notif.from_user = doc.owner or "Administrator"
			notif.to_user = assigned_user
			notif.type = "WhatsApp"
			notif.message = f"New WhatsApp message from {cust_label}: {msg_preview}"
			notif.notification_text = f"WhatsApp Message from {cust_label}: {msg_preview}"
			notif.notification_type_doctype = "WhatsApp Message"
			notif.notification_type_doc = doc.name
			notif.reference_doctype = "CRM Lead"
			notif.reference_name = doc.reference_docname
			notif.read = 0
			notif.insert(ignore_permissions=True)


def on_whatsapp_message_update(doc, method=None):
	"""
	Hook for WhatsApp Message on_update:
	Publish realtime event so status updates (delivered, read, reaction) reflect immediately.
	"""
	if doc.reference_doctype and doc.reference_docname:
		frappe.publish_realtime(
			"whatsapp_message",
			{
				"reference_doctype": doc.reference_doctype,
				"reference_name": doc.reference_docname,
				"status": doc.get("status"),
				"name": doc.name,
			},
		)
