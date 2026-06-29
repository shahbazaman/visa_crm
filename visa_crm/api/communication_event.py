import frappe


from visa_crm.api.customer_matcher import match_all




def create_communication_event(

        call_doc

):



    matches = match_all(

        call_doc.customer_phone_extracted

    )



    event = frappe.get_doc({


        "doctype":

            "Communication Event",



        "source":

            "Phone",



        "event_type":

            "Call",



        "direction":

            "Inbound",



        "customer":

            matches["customer"],



        "lead":

            matches["lead"],



        "employee":

            matches["employee"],



        "call_intelligence":

            call_doc.name,



        "phone":

            call_doc.customer_phone_extracted,



        "summary":

            call_doc.summary,



        "sentiment":

            call_doc.sentiment,



        "lead_score":

            call_doc.lead_score,



        "recording_file":

            call_doc.recording_file,



        "duration":

            call_doc.call_duration,



        "event_datetime":

            frappe.utils.now_datetime()



    })



    event.insert(


        ignore_permissions=True


    )



    frappe.db.commit()



    return event.name

