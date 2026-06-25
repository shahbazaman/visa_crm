import frappe
import json


@frappe.whitelist(allow_guest=True)
def meta_verify():

    mode = frappe.request.args.get("hub.mode")
    token = frappe.request.args.get("hub.verify_token")
    challenge = frappe.request.args.get("hub.challenge")

    name = frappe.get_all(
        "Meta Settings",
        pluck="name",
        limit=1
    )[0]

    settings = frappe.get_doc(
        "Meta Settings",
        name
    )

    saved = settings.get_password("verify_token")


    frappe.logger().info(f"""
    META DEBUG
    mode={mode}
    token_repr={repr(token)}
    saved_token_repr={repr(saved)}
    comparison={token == saved}
    challenge={challenge}
    """)


    if mode == "subscribe" and token == saved:

        frappe.response["type"] = "txt"

        frappe.response["doctype"] = "meta"

        frappe.response["result"] = challenge

        return


    frappe.response["type"] = "txt"

    frappe.response["doctype"] = "meta"

    frappe.response["result"] = "Verification failed"

    frappe.response["http_status_code"] = 403




@frappe.whitelist(allow_guest=True)
def receive():

    payload = frappe.request.get_json()


    lead_source = "Meta Ads"

    if payload.get("object") == "page":
        lead_source = "Meta Instant Form"


    queue = frappe.get_doc({

        "doctype": "Lead Intake Queue",

        "lead_source": lead_source,

        "raw_payload": json.dumps(payload),

        "status": "Lead Received"

    })


    queue.insert(ignore_permissions=True)

    frappe.db.commit()


    return {

        "success": True

    }