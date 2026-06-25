import frappe
import json


@frappe.whitelist(allow_guest=True)
def meta_verify():

    mode = frappe.request.args.get("hub.mode")
    token = frappe.request.args.get("hub.verify_token")
    challenge = frappe.request.args.get("hub.challenge")

    names = frappe.get_all(
        "Meta Settings",
        pluck="name",
        limit=1
    )

    if not names:

        frappe.log_error(
            title="META DEBUG",
            message="No Meta Settings found"
        )

        frappe.response["http_status_code"] = 403

        return "Meta Settings not found"


    settings = frappe.get_doc(
        "Meta Settings",
        names[0]
    )

    saved = settings.get_password("verify_token")


    frappe.log_error(

        title="META DEBUG",

        message=f"""
mode={mode}

token={token}

challenge={challenge}

token_repr={repr(token)}

saved_token_repr={repr(saved)}

comparison={token == saved}

settings_name={settings.name}

request_args={dict(frappe.request.args)}
"""

    )


    if mode == "subscribe" and token == saved:

        frappe.local.response["type"] = "txt"

        frappe.local.response["filename"] = None

        frappe.local.response["response"] = challenge

        return


    frappe.response["http_status_code"] = 403

    return "Verification failed"



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