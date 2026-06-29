import frappe




def create_score_history(

        call_doc

):



    history = frappe.get_doc({



        "doctype":

            "Lead Score History",



        "lead":

            call_doc.lead_match,



        "customer":

            call_doc.customer_360_match,



        "employee":

            call_doc.employee_match,



        "score":

            call_doc.lead_score,



        "emotion":

            call_doc.sentiment,



        "intent":

            call_doc.lead_intent,



        "call_intelligence":

            call_doc.name,



        "recorded_on":

            frappe.utils.now_datetime()



    })



    history.insert(


        ignore_permissions=True


    )


    frappe.db.commit()



    return history.name
