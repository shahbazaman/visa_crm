
# Seamlessly guard CRM's legacy WhatsApp validate method against missing attributes
try:
	import crm.api.whatsapp
	_orig_crm_whatsapp_validate = getattr(crm.api.whatsapp, "validate", None)

	def safe_crm_whatsapp_validate(doc, method=None):
		dir_val = getattr(doc, "direction", None) or doc.get("direction") or getattr(doc, "type", None) or doc.get("type") or "Outgoing"
		doc.direction = dir_val
		doc.type = dir_val
		if getattr(doc, "reference_docname", None):
			doc.reference_name = doc.reference_docname
		elif getattr(doc, "reference_name", None):
			doc.reference_docname = doc.reference_name
		if _orig_crm_whatsapp_validate:
			try:
				return _orig_crm_whatsapp_validate(doc, method)
			except Exception:
				pass

	crm.api.whatsapp.validate = safe_crm_whatsapp_validate
except Exception:
	pass

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



def on_whatsapp_message_before_validate(doc, method=None):
	"""
	Ensure doc.type and doc.direction are always populated before validation.
	"""
	dir_val = getattr(doc, "direction", None) or doc.get("direction") or getattr(doc, "type", None) or doc.get("type") or "Outgoing"
	doc.direction = dir_val
	doc.type = dir_val
	if getattr(doc, "reference_docname", None):
		doc.reference_name = doc.reference_docname
	elif getattr(doc, "reference_name", None):
		doc.reference_docname = doc.reference_name


def on_whatsapp_message_validate(doc, method=None):
	"""
	Hook for WhatsApp Message validate:
	1. Guarantee doc.type and doc.direction compatibility.
	2. Resolve phone number from message (from or to).
	3. Link to CRM Lead or Customer if not already set.
	4. Prevent duplicate incoming messages using message_id idempotency.
	"""
	on_whatsapp_message_before_validate(doc, method)

	# Deduplicate incoming webhook messages
	if getattr(doc, "direction", "") == "Incoming" or getattr(doc, "type", "") == "Incoming":
		if doc.message_id and not doc.is_new():
			return

	# If reference is already set, do not override
	if (doc.reference_doctype and doc.reference_docname) or (doc.reference_doctype and getattr(doc, "reference_name", None)):
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
		doc.reference_name = matched_lead
		return

	# Find matching Customer
	matched_customer = find_matching_customer(phone_val)
	if matched_customer:
		doc.reference_doctype = "Customer"
		doc.reference_docname = matched_customer
		doc.reference_name = matched_customer


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

def get_or_create_whatsapp_profile(phone: str, whatsapp_account: str, profile_name: str = None) -> str:
	"""
	Resolve or create a WhatsApp Profile for a given phone number.
	"""
	normalized = normalize_phone_number(phone)
	if not normalized:
		normalized = str(phone).strip()

	if not frappe.db.exists("DocType", "WhatsApp Profile"):
		return normalized

	# Check by phone_number and whatsapp_account
	existing = frappe.db.get_value(
		"WhatsApp Profile",
		{"phone_number": normalized, "whatsapp_account": whatsapp_account},
		"name",
	)
	if existing:
		return existing

	# Fallback: check by phone_number alone
	existing = frappe.db.get_value("WhatsApp Profile", {"phone_number": normalized}, "name")
	if existing:
		return existing

	# Create new WhatsApp Profile
	try:
		profile = frappe.new_doc("WhatsApp Profile")
		profile.phone_number = normalized
		profile.profile_name = profile_name or normalized
		profile.whatsapp_account = whatsapp_account
		profile.status = "Active"
		profile.insert(ignore_permissions=True)
		return profile.name
	except Exception:
		return normalized


@frappe.whitelist()
def get_whatsapp_messages(reference_doctype: str, reference_name: str):
	"""
	CRM API bridge: returns normalized conversation messages for the CRM Lead / Deal Vue SPA.
	Handles both official frappe/whatsapp and native CRM schemas.
	"""
	validate_access(reference_doctype, reference_name)
	if not frappe.db.exists("DocType", "WhatsApp Message"):
		return []

	# Check if reference doc is CRM Deal with linked lead
	lead_name = None
	if reference_doctype == "CRM Deal":
		deal_doc = frappe.get_doc(reference_doctype, reference_name)
		lead_name = deal_doc.get("lead")

	# Fetch messages matching reference_doctype and reference_docname
	or_filters = [
		{"reference_doctype": reference_doctype, "reference_docname": reference_name}
	]
	if lead_name:
		or_filters.append({"reference_doctype": "CRM Lead", "reference_docname": lead_name})

	# Query WhatsApp Messages with safe field fallback
	all_messages = []
	for f in or_filters:
		try:
			msgs = frappe.get_all(
				"WhatsApp Message",
				filters=f,
				fields=[
					"name",
					"direction",
					"to",
					"from",
					"message",
					"attach",
					"status",
					"message_id",
					"context_message_id",
					"reply_to_message",
					"creation",
					"reference_doctype",
					"reference_docname",
					"is_template",
					"whatsapp_template",
				],
				order_by="creation asc",
			)
			all_messages.extend(msgs)
		except Exception:
			# In case table has legacy schema
			try:
				msgs = frappe.get_all("WhatsApp Message", filters=f, fields=["*"], order_by="creation asc")
				all_messages.extend(msgs)
			except Exception:
				pass

	# Format messages for Frappe CRM Frontend (Vue SPA)
	formatted = []
	ref_title = reference_name
	try:
		ref_doc = frappe.get_doc(reference_doctype, reference_name)
		ref_title = ref_doc.get("lead_name") or ref_doc.get("customer_name") or reference_name
	except Exception:
		pass

	for m in all_messages:
		direction = m.get("direction") or m.get("type") or "Outgoing"
		from_val = m.get("from")
		to_val = m.get("to")
		from_name = _("You") if direction == "Outgoing" else ref_title

		formatted.append({
			"name": m.get("name"),
			"type": direction,  # Frontend checks msg.type == 'Outgoing' / 'Incoming'
			"direction": direction,
			"to": to_val,
			"from": from_val,
			"from_name": from_name,
			"message": m.get("message") or "",
			"status": m.get("status") or "Sent",
			"creation": m.get("creation"),
			"attach": m.get("attach") or "",
			"content_type": "text" if not m.get("attach") else "document",
			"message_id": m.get("message_id") or "",
			"is_reply": bool(m.get("context_message_id") or m.get("reply_to_message")),
			"reply_to_message_id": m.get("context_message_id") or "",
			"reply_to": m.get("reply_to_message") or "",
			"reply_to_type": "Incoming" if direction == "Outgoing" else "Outgoing",
			"reply_to_from": ref_title if direction == "Outgoing" else _("You"),
			"reply_message": "",
			"reaction": m.get("reaction") or "",
			"reference_doctype": m.get("reference_doctype"),
			"reference_name": m.get("reference_docname") or m.get("reference_name"),
		})

	return formatted


@frappe.whitelist()
def create_whatsapp_message(
	reference_doctype: str,
	reference_name: str,
	message: str,
	to: str,
	attach: str = "",
	reply_to: str = "",
	content_type: str = "text",
):
	"""
	CRM API bridge: creates and dispatches an outgoing WhatsApp message.
	"""
	validate_access(reference_doctype, reference_name)

	default_account = get_default_whatsapp_account()

	lead_title = reference_name
	try:
		lead_doc = frappe.get_doc(reference_doctype, reference_name)
		lead_title = lead_doc.get("lead_name") or lead_doc.get("customer_name") or to
	except Exception:
		pass

	profile_name = get_or_create_whatsapp_profile(to, default_account, lead_title)

	doc = frappe.new_doc("WhatsApp Message")
	doc.whatsapp_account = default_account
	doc.to = profile_name
	doc.direction = "Outgoing"
	doc.status = "Pending"
	doc.message = message or attach or ""
	doc.attach = attach or ""
	doc.reference_doctype = reference_doctype
	doc.reference_docname = reference_name

	if reply_to and frappe.db.exists("WhatsApp Message", reply_to):
		try:
			reply_doc = frappe.get_doc("WhatsApp Message", reply_to)
			doc.context_message_id = reply_doc.get("message_id")
			doc.reply_to_message = reply_doc.name
		except Exception:
			pass

	doc.insert(ignore_permissions=True)

	# If WhatsApp Account has access_token and phone_id, attempt submission
	try:
		acc_token = frappe.db.get_value("WhatsApp Account", default_account, "access_token")
		if hasattr(doc, "submit") and acc_token:
			doc.submit()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "CRM WhatsApp Outgoing Dispatch")

	return doc.name

@frappe.whitelist()
def send_whatsapp_template(reference_doctype: str, reference_name: str, template: str, to: str):
	"""
	CRM API bridge: sends a WhatsApp template message.
	"""
	validate_access(reference_doctype, reference_name)

	default_account = get_default_whatsapp_account()

	lead_title = reference_name
	try:
		lead_doc = frappe.get_doc(reference_doctype, reference_name)
		lead_title = lead_doc.get("lead_name") or lead_doc.get("customer_name") or to
	except Exception:
		pass

	profile_name = get_or_create_whatsapp_profile(to, default_account, lead_title)

	doc = frappe.new_doc("WhatsApp Message")
	doc.whatsapp_account = default_account
	doc.to = profile_name
	doc.direction = "Outgoing"
	doc.status = "Pending"
	doc.is_template = 1
	doc.whatsapp_template = template
	doc.reference_doctype = reference_doctype
	doc.reference_docname = reference_name
	doc.insert(ignore_permissions=True)

	try:
		acc_token = frappe.db.get_value("WhatsApp Account", default_account, "access_token")
		if hasattr(doc, "submit") and acc_token:
			doc.submit()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "CRM WhatsApp Template Dispatch")

	return doc.name

@frappe.whitelist()
def react_on_whatsapp_message(emoji: str, reply_to_name: str):
	"""
	CRM API bridge: reacts to a WhatsApp message with an emoji.
	"""
	validate_access()
	if not frappe.db.exists("WhatsApp Message", reply_to_name):
		frappe.throw(_("Referenced WhatsApp message does not exist."), frappe.DoesNotExistError)

	msg_doc = frappe.get_doc("WhatsApp Message", reply_to_name)
	msg_doc.reaction = emoji
	msg_doc.save(ignore_permissions=True)

	frappe.publish_realtime(
		"whatsapp_message",
		{
			"reference_doctype": msg_doc.reference_doctype,
			"reference_name": msg_doc.reference_docname,
			"reaction": emoji,
			"name": msg_doc.name,
		},
	)
	return msg_doc.name


def get_default_whatsapp_account(auto_create: bool = True) -> str:
	"""
	Safely retrieve or auto-initialize an active WhatsApp Account.
	"""
	# 1. Try single settings
	for field in ("default_account", "default_outgoing_account"):
		try:
			acc = frappe.db.get_single_value("WhatsApp Settings", field)
			if acc and frappe.db.exists("WhatsApp Account", acc):
				return acc
		except Exception:
			pass

	# 2. Try any active WhatsApp Account
	try:
		accounts = frappe.get_all("WhatsApp Account", filters={"status": "Active"}, limit=1)
		if accounts:
			return accounts[0].name
	except Exception:
		pass

	# 3. Try any existing WhatsApp Account
	try:
		accounts = frappe.get_all("WhatsApp Account", limit=1)
		if accounts:
			acc_name = accounts[0].name
			if auto_create:
				try:
					frappe.db.set_value("WhatsApp Account", acc_name, "status", "Active")
				except Exception:
					pass
			return acc_name
	except Exception:
		pass

	if not auto_create:
		return ""

	# 4. Auto-create 'Primary WhatsApp' account
	try:
		acc = frappe.new_doc("WhatsApp Account")
		acc.account_name = "Primary WhatsApp"
		acc.status = "Active"
		acc.insert(ignore_permissions=True)
		return acc.name
	except Exception:
		return "Primary WhatsApp"


@frappe.whitelist(allow_guest=True)
def is_whatsapp_enabled() -> bool:
	"""
	Universal fault-tolerant WhatsApp enabled checker for Frappe CRM v1.82.
	"""
	if not frappe.db.exists("DocType", "WhatsApp Settings") or not frappe.db.exists("DocType", "WhatsApp Account"):
		return False

	acc = get_default_whatsapp_account(auto_create=False)
	return bool(acc)

@frappe.whitelist(allow_guest=True)
def is_whatsapp_installed() -> bool:
	"""
	Universal WhatsApp installed checker for Frappe CRM.
	"""
	return bool(
		frappe.db.exists("DocType", "WhatsApp Settings")
		and frappe.db.exists("DocType", "WhatsApp Message")
	)
