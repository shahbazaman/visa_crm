import frappe
import json


@frappe.whitelist(allow_guest=True)
def meta_verify():

    mode = frappe.form_dict.get("hub.mode")
    token = frappe.form_dict.get("hub.verify_token")
    challenge = frappe.form_dict.get("hub.challenge")


    settings_name = frappe.get_all(
        "Meta Settings",
        pluck="name",
        limit=1
    )


    if not settings_name:
        frappe.throw("Meta Settings not found")


    settings = frappe.get_doc(
        "Meta Settings",
        settings_name[0]
    )


    if (
        mode == "subscribe"
        and token == settings.verify_token
    ):

        frappe.response["type"] = "text"
        frappe.response["message"] = challenge
        return


    frappe.throw("Verification failed")



@frappe.whitelist(allow_guest=True)
def receive():

    payload = frappe.request.get_json()


    lead_source = "Meta Ads"

    if payload.get("object") == "page":
        lead_source = "Meta Instant Form"



    queue = frappe.get_doc({

        "doctype":"Lead Intake Queue",

        "lead_source":lead_source,

        "raw_payload":json.dumps(payload),

        "status":"Lead Received"

    })


    queue.insert(ignore_permissions=True)

    frappe.db.commit()


    return {
        "success":True
    }