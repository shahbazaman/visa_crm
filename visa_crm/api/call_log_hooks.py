# Copyright (c) 2026, Shahbaz and contributors
# For license information, please see license.txt

import frappe


def auto_populate_call_log_phone(doc, method=None):
	"""
	Automatically populate the customer's phone/mobile number from CRM Lead
	into the Call Log's contact/number field (to or from) when creating a call log.
	Preserves editability and never overwrites user-entered values.
	"""
	if not doc.reference_doctype or doc.reference_doctype != "CRM Lead" or not doc.reference_docname:
		return

	# If phone number is already filled by user, do not overwrite
	if doc.type == "Incoming" and doc.get("from"):
		return
	if doc.type != "Incoming" and doc.get("to"):
		return

	if not frappe.db.exists("CRM Lead", doc.reference_docname):
		return

	lead = frappe.db.get_value(
		"CRM Lead",
		doc.reference_docname,
		["mobile_no", "phone"],
		as_dict=True,
	)
	if not lead:
		return

	phone_number = lead.get("mobile_no") or lead.get("phone") or ""
	phone_number = str(phone_number).strip() if phone_number else ""

	if not phone_number:
		return

	if doc.type == "Incoming":
		if not doc.get("from"):
			doc.set("from", phone_number)
	else:
		if not doc.get("to"):
			doc.to = phone_number


def setup_call_log_form_script():
	"""
	Ensure a standard CRM Form Script exists for CRM Call Log so the Quick Entry
	dialog in the CRM Vue SPA pre-fills customer phone from the Lead.
	"""
	script_code = """
export default async function setupForm({ doc, call }) {
  if (!doc.name && doc.reference_doctype === 'CRM Lead' && doc.reference_docname) {
    if (!doc.to && !doc.from) {
      let r = await call('frappe.client.get_value', {
        doctype: 'CRM Lead',
        fieldname: ['mobile_no', 'phone'],
        filters: { name: doc.reference_docname }
      });
      let lead = r?.message;
      let phone = lead?.mobile_no || lead?.phone || '';
      if (phone) {
        if (doc.type === 'Incoming') {
          if (!doc.from) doc.from = phone;
        } else {
          if (!doc.to) doc.to = phone;
        }
      }
    }
  }
}
"""
	if frappe.db.exists("CRM Form Script", {"dt": "CRM Call Log", "view": "Form"}):
		doc_name = frappe.db.get_value("CRM Form Script", {"dt": "CRM Call Log", "view": "Form"})
		script_doc = frappe.get_doc("CRM Form Script", doc_name)
		if script_code not in (script_doc.script or ""):
			script_doc.script = script_code
			script_doc.enabled = 1
			script_doc.save(ignore_permissions=True)
	else:
		script_doc = frappe.new_doc("CRM Form Script")
		script_doc.dt = "CRM Call Log"
		script_doc.view = "Form"
		script_doc.enabled = 1
		script_doc.is_standard = 0
		script_doc.script = script_code
		script_doc.insert(ignore_permissions=True)
