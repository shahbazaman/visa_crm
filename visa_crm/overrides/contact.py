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
		rows = [
			"name",
			"full_name",
			"customer_name",
			"lead_category",
			"lead_group",
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

		contact_names = [d.get("name") for d in data if d.get("name")]
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

		# For contacts without direct dynamic link, match by email or mobile
		contacts_missing_lead = [d for d in data if d.get("name") not in lead_map]
		if contacts_missing_lead:
			emails = [d.get("email_id") for d in contacts_missing_lead if d.get("email_id")]
			phones = [d.get("mobile_no") for d in contacts_missing_lead if d.get("mobile_no")]

			if emails or phones:
				lead_matches = frappe.db.sql("""
					SELECT name, email, mobile_no, lead_name, first_name, lead_category, lead_group
					FROM `tabCRM Lead`
					WHERE (email IS NOT NULL AND email != '' AND email IN %(emails)s)
					   OR (mobile_no IS NOT NULL AND mobile_no != '' AND mobile_no IN %(phones)s)
				""", {"emails": emails or ["-none-"], "phones": phones or ["-none-"]}, as_dict=True)

				email_to_lead = {l.email: l for l in lead_matches if l.email}
				phone_to_lead = {l.mobile_no: l for l in lead_matches if l.mobile_no}

				for d in contacts_missing_lead:
					c_name = d.get("name")
					if d.get("email_id") in email_to_lead:
						lead_map[c_name] = email_to_lead[d["email_id"]].name
					elif d.get("mobile_no") in phone_to_lead:
						lead_map[c_name] = phone_to_lead[d["mobile_no"]].name

		# Batch fetch CRM Lead details
		lead_details = {}
		unique_lead_names = list(set(lead_map.values()))
		if unique_lead_names:
			leads = frappe.db.sql("""
				SELECT name, lead_name, first_name, lead_category, lead_group
				FROM `tabCRM Lead`
				WHERE name IN %(lead_names)s
			""", {"lead_names": unique_lead_names}, as_dict=True)
			lead_details = {l.name: l for l in leads}

		# Batch fetch Customer details
		customer_details = {}
		unique_cust_names = list(set(customer_map.values()))
		if unique_cust_names:
			customers = frappe.db.sql("""
				SELECT name, customer_name
				FROM `tabCustomer`
				WHERE name IN %(cust_names)s
			""", {"cust_names": unique_cust_names}, as_dict=True)
			customer_details = {c.name: c for c in customers}

		for d in data:
			c_name = d.get("name")
			linked_lead_name = lead_map.get(c_name)
			linked_cust_name = customer_map.get(c_name)

			lead_info = lead_details.get(linked_lead_name) if linked_lead_name else None
			cust_info = customer_details.get(linked_cust_name) if linked_cust_name else None

			# Customer Name: priority Customer.customer_name -> CRM Lead.lead_name -> Contact.full_name
			if cust_info and cust_info.get("customer_name"):
				d["customer_name"] = cust_info["customer_name"]
			elif lead_info and (lead_info.get("lead_name") or lead_info.get("first_name")):
				d["customer_name"] = lead_info.get("lead_name") or lead_info.get("first_name")
			else:
				d["customer_name"] = d.get("full_name") or ""

			# Category and Subcategory from CRM Lead
			d["lead_category"] = (lead_info.get("lead_category") if lead_info else "") or ""
			d["lead_group"] = (lead_info.get("lead_group") if lead_info else "") or ""

		return data
