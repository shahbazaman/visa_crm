import frappe


def create_followup(lead):

    todo=frappe.get_doc({

        "doctype":"ToDo",

        "description":f"Call {lead.lead_name}",

        "reference_type":"Lead",

        "reference_name":lead.name,

        "allocated_to":"Administrator"

    })

    todo.insert(ignore_permissions=True)