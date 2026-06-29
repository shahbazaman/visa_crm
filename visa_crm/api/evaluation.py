import frappe




def create_employee_evaluation(

        call_doc

):



    if not call_doc.employee_match:

        return




    doc = frappe.get_doc({


        "doctype":

            "Employee Evaluation",




        "employee":

            call_doc.employee_match,




        "communication_event":

            call_doc.communication_event,




        "friendliness":

            call_doc.friendliness_score,




        "professionalism":

            call_doc.professionalism_score,




        "empathy":

            call_doc.empathy_score,




        "clarity":

            call_doc.clarity,




        "responsiveness":

            call_doc.responsiveness,




        "policy_compliance":

            call_doc.policy_compliance,




        "overall_score":

            call_doc.overall_score,




        "ai_feedback":

            call_doc.ai_feedback,




        "coaching_tips":

            call_doc.coaching_tips



    })



    doc.insert(


        ignore_permissions=True


    )



    frappe.db.commit()



    return doc.name
