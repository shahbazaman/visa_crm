# Copyright (c) 2026, Shahbaz and contributors
# For license information, please see license.txt

import frappe
from frappe.contacts.doctype.contact.contact import Contact


class VisaCRMContact(Contact):
	@staticmethod
	def default_list_data():
		columns = [
			{
				"label": "Name",
				"type": "Data",
				"key": "full_name",
				"width": "14rem",
			},
			{
				"label": "Customer Name",
				"type": "Data",
				"key": "customer_name",
				"width": "14rem",
			},
			{
				"label": "Category",
				"type": "Data",
				"key": "lead_category",
				"width": "11rem",
			},
			{
				"label": "Subcategory",
				"type": "Data",
				"key": "lead_group",
				"width": "11rem",
			},
			{
				"label": "Email",
				"type": "Data",
				"key": "email_id",
				"width": "12rem",
			},
			{
				"label": "Phone",
				"type": "Data",
				"key": "mobile_no",
				"width": "11rem",
			},
			{
				"label": "Organization",
				"type": "Data",
				"key": "company_name",
				"width": "11rem",
			},
			{
				"label": "Last Modified",
				"type": "Datetime",
				"key": "modified",
				"width": "8rem",
			},
		]
		# rows must only contain fields that exist on tabContact in MySQL
		rows = [
			"name",
			"full_name",
			"company_name",
			"email_id",
			"mobile_no",
			"modified",
			"image",
		]
		return {"columns": columns, "rows": rows}

	@staticmethod
	def parse_list_data(data):
		if not data:
			return data

		contact_names = [d.get("name") for d in data if isinstance(d, dict) and d.get("name")]
		if not contact_names:
			return data

		# Batch query dynamic links to find linked CRM Leads and Customers
		links = frappe.db.sql("""
			SELECT parent, link_doctype, link_name
			FROM `tabDynamic Link`
			WHERE parenttype = 'Contact'
			  AND parent IN %(names)s
			  AND link_doctype IN ('CRM Lead', 'Customer')
		""", {"names": contact_names}, as_dict=True)

		lead_map = {}
		customer_map = {}
		for link in links:
			if link.link_doctype == "CRM Lead" and link.parent not in lead_map:
				lead_map[link.parent] = link.link_name
			elif link.link_doctype == "Customer" and link.parent not in customer_map:
				customer_map[link.parent] = link.link_name

		lead_details = {}
		if lead_map:
			lead_records = frappe.db.sql("""
				SELECT name, lead_name, first_name, last_name, lead_category, lead_group
				FROM `tabCRM Lead`
				WHERE name IN %(lead_names)s
			""", {"lead_names": list(lead_map.values())}, as_dict=True)

			for l in lead_records:
				name_val = l.lead_name or " ".join(filter(None, [l.first_name, l.last_name])) or l.name
				lead_details[l.name] = {
					"customer_name": name_val,
					"lead_category": l.lead_category or "",
					"lead_group": l.lead_group or "",
				}

		customer_details = {}
		if customer_map:
			cust_records = frappe.db.sql("""
				SELECT name, customer_name
				FROM `tabCustomer`
				WHERE name IN %(cust_names)s
			""", {"cust_names": list(customer_map.values())}, as_dict=True)

			for c in cust_records:
				customer_details[c.name] = {
					"customer_name": c.customer_name or c.name,
					"lead_category": "",
					"lead_group": "",
				}

		for item in data:
			if not isinstance(item, dict):
				continue
			c_name = item.get("name")
			if c_name in lead_map and lead_map[c_name] in lead_details:
				det = lead_details[lead_map[c_name]]
				item["customer_name"] = det["customer_name"]
				item["lead_category"] = det["lead_category"]
				item["lead_group"] = det["lead_group"]
			elif c_name in customer_map and customer_map[c_name] in customer_details:
				det = customer_details[customer_map[c_name]]
				item["customer_name"] = det["customer_name"]
				item["lead_category"] = ""
				item["lead_group"] = ""
			else:
				item["customer_name"] = item.get("full_name") or ""
				item["lead_category"] = ""
				item["lead_group"] = ""

		return data
