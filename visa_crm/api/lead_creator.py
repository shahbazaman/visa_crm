import frappe


def create_lead(queue):

    lead=frappe.get_doc({

        "doctype":"Lead",

        "lead_name":queue.customer_name,

        "mobile_no":queue.phone,

        "email_id":queue.email,

        "source":queue.lead_source,

        "status":"Open"

    })

    lead.insert(ignore_permissions=True)

    return lead