import frappe
import json


@frappe.whitelist(allow_guest=True)
def meta_verify():

    mode=frappe.form_dict.get("hub.mode")
    token=frappe.form_dict.get("hub.verify_token")
    challenge=frappe.form_dict.get("hub.challenge")


    frappe.log_error(
        title="META VERIFY",
        message=f"""
mode={mode}

token={token}

challenge={challenge}
"""
    )


    settings=frappe.get_all(
        "Meta Settings",
        fields=["name","verify_token"]
    )


    frappe.log_error(
        title="META SETTINGS",
        message=str(settings)
    )


    return "OK"



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