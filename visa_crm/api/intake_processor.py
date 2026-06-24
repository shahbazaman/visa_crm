import frappe
import json




def process_queue(docname):

    doc = frappe.get_doc(
        "Lead Intake Queue",
        docname
    )

    payload = json.loads(

        doc.raw_payload

    )
    lead_data = payload["entry"][0]["changes"][0]["value"]
    leadgen_id = lead_data.get("leadgen_id")




def process_pending():



    docs = frappe.get_all(

        "Lead Intake Queue",

        filters={

            "status":"Pending"

        },

        fields=["name"]

    )



    for d in docs:



        process_queue(

            d.name

        )


