# Copyright (c) 2026, Shahbaz and contributors
# For license information, please see license.txt

import json
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	"""
	Ensure suggestion_or_requirement Custom Field is created on CRM Lead
	and included in the CRM Lead-Side Panel layout.
	"""
	custom_fields = {
		"CRM Lead": [
			{
				"fieldname": "suggestion_or_requirement",
				"label": "Suggestion or Requirement",
				"fieldtype": "Long Text",
				"insert_after": "source",
				"in_list_view": 0,
				"in_standard_filter": 0,
			}
		]
	}
	create_custom_fields(custom_fields, ignore_validate=True)

	# Update CRM Fields Layout for CRM Lead-Side Panel if exists
	layout_name = frappe.db.get_value("CRM Fields Layout", {"dt": "CRM Lead", "type": "Side Panel"})
	if layout_name:
		layout_doc = frappe.get_doc("CRM Fields Layout", layout_name)
		try:
			layout_data = json.loads(layout_doc.layout)
			modified = False
			for section in layout_data:
				if section.get("name") == "details_section":
					for column in section.get("columns", []):
						fields = column.get("fields", [])
						if "suggestion_or_requirement" not in fields:
							if "source" in fields:
								idx = fields.index("source") + 1
								fields.insert(idx, "suggestion_or_requirement")
							else:
								fields.append("suggestion_or_requirement")
							column["fields"] = fields
							modified = True
			if modified:
				layout_doc.layout = json.dumps(layout_data)
				layout_doc.save(ignore_permissions=True)
		except Exception as e:
			frappe.log_error(f"Error updating CRM Lead-Side Panel layout: {e}", "Suggestion Field Setup")
