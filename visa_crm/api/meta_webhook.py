import frappe
import json

from visa_crm.api.meta_graph import fetch_lead
@frappe.whitelist(allow_guest=True)
def webhook():

    frappe.log_error(
        title="META WEBHOOK ENTRY",
        message=f"""
method={frappe.request.method}

headers={dict(frappe.request.headers)}

args={dict(frappe.request.args)}

form_dict={dict(frappe.form_dict)}
"""
    )

    try:

        # if frappe.request.method == "GET":
        #     return meta_verify()

        # return receive()
        if frappe.request.method == "GET":
            return meta_verify()

        if frappe.request.method == "POST":
            return receive()

        frappe.response["http_status_code"] = 405
        return "Method Not Allowed"        

    except Exception:

        frappe.log_error(

            title="META WEBHOOK CRASH",

            message=frappe.get_traceback()

        )

        frappe.response["http_status_code"] = 500

        return "Webhook crashed"



def meta_verify():

    try:

        mode = frappe.request.args.get("hub.mode")

        token = frappe.request.args.get("hub.verify_token")

        challenge = frappe.request.args.get("hub.challenge")


        frappe.log_error(

            title="META VERIFY INPUT",

            message=f"""
mode={repr(mode)}

token={repr(token)}

challenge={repr(challenge)}
"""

        )


        settings_name = frappe.get_all(

            "Meta Settings",

            pluck="name",

            limit=1

        )


        frappe.log_error(

            title="META SETTINGS LOOKUP",

            message=str(settings_name)

        )


        if not settings_name:

            frappe.log_error(

                title="META VERIFY ERROR",

                message="Meta Settings not found"

            )

            return "Verification failed"



        settings = frappe.get_doc(

            "Meta Settings",

            settings_name[0]

        )


        saved = settings.get_password(

            "verify_token"

        )


        frappe.log_error(

            title="META TOKEN CHECK",

            message=f"""
settings_doc={settings.name}

token_repr={repr(token)}

saved_repr={repr(saved)}

comparison={token==saved}
"""

        )


        if mode == "subscribe" and token == saved:


            frappe.log_error(

                title="META VERIFY SUCCESS",

                message=f"""
challenge={challenge}
"""

            )


            response = frappe.response

            response["type"] = "txt"

            response["doctype"] = "meta"

            response["filename"] = "challenge"

            response["result"] = challenge

            return



        frappe.log_error(

            title="META VERIFY FAILED",

            message=f"""
mode={mode}

token={repr(token)}

saved={repr(saved)}
"""

        )


        frappe.response["http_status_code"] = 403


        response = frappe.response

        response["type"] = "txt"

        response["doctype"] = "meta"

        response["filename"] = "error"

        response["result"] = "Verification failed"

        return


    except Exception:


        frappe.log_error(

            title="META VERIFY EXCEPTION",

            message=frappe.get_traceback()

        )

        return "Verification Exception"




def receive():

    try:


        raw_data = frappe.request.data


        frappe.log_error(

            title="META RAW BODY",

            message=str(raw_data)

        )



        payload = frappe.request.get_json(

            silent=True

        )



        frappe.log_error(

            title="META JSON PARSE",

            message=str(payload)

        )



        if not payload:

            payload = dict(

                frappe.form_dict

            )



        frappe.log_error(

            title="META FORM DICT",

            message=json.dumps(

                payload,

                indent=2,

                default=str

            )

        )



        if not payload:

            payload = raw_data.decode(

                "utf-8"

            )



        frappe.log_error(

            title="META RECEIVE",

            message=json.dumps(

                payload,

                indent=2,

                default=str

            )

        )



        lead_source = "Meta Ads"



        if isinstance(

            payload,

            dict

        ):


            if payload.get(

                "object"

            ) == "page":


                lead_source = (

                    "Meta Instant Form"

                )



        frappe.log_error(

            title="META LEAD SOURCE",

            message=lead_source

        )

        leadgen_id=None

        try:
            leadgen_id=payload["entry"][0]["changes"][0]["value"]["leadgen_id"]
        except:
            pass

        lead_data=None
        if leadgen_id:
            lead_data=fetch_lead(leadgen_id)

        queue=frappe.get_doc({
        "doctype":"Lead Intake Queue",
        "lead_source":lead_source,
        "source_lead_id":leadgen_id,
        "raw_payload":json.dumps(payload,default=str),
        "status":"Lead Received"
        })

        if lead_data:
            for f in lead_data.get("field_data",[]):
                n=f.get("name")
                v=f.get("values",[None])[0]
                if n=="full_name":
                    queue.customer_name=v
                elif n=="phone_number":
                    queue.phone=v
                elif n=="email":
                    queue.email=v
                elif "country" in n.lower():
                    queue.country_interested=v
                elif "visa" in n.lower():
                    queue.visa_type=v
        frappe.log_error(

            title="META QUEUE DOC",

            message=str(queue.as_dict())

        )



        queue.insert(

            ignore_permissions=True

        )

        fetch_lead_details(
            payload,
            queue.name
        )

        frappe.log_error(

            title="META INSERTED",

            message=queue.name

        )



        frappe.db.commit()



        frappe.log_error(

            title="META COMMIT",

            message="success"

        )



        return {

            "success": True

        }



    except Exception:



        frappe.log_error(

            title="META RECEIVE EXCEPTION",

            message=frappe.get_traceback()

        )



        return {

            "success": False

        }