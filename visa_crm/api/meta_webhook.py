import frappe
import json


@frappe.whitelist(allow_guest=True)

def meta_verify():

    mode=frappe.form_dict.get("hub.mode")

    token=frappe.form_dict.get("hub.verify_token")

    challenge=frappe.form_dict.get("hub.challenge")

    settings=frappe.get_all(

    "Meta Settings",

    limit=1
    )

    print(settings)



    if mode=="subscribe" and token==settings.verify_token:

        frappe.response["type"]="text"

        frappe.response["message"]=challenge

        return


    frappe.throw("Verification failed")




@frappe.whitelist(allow_guest=True)

def receive():

    payload=frappe.request.get_json()


    queue=frappe.get_doc({

        "doctype":"Lead Intake Queue",

        "lead_source":"Facebook Ads",

        "raw_payload":json.dumps(payload),

        "status":"Lead Received"

    })


    queue.insert(ignore_permissions=True)


    frappe.db.commit()


    frappe.response["type"]="json"

    frappe.response["message"]={

        "success":True

    }
