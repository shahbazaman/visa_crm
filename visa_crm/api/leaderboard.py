import frappe




def update_leaderboard():



    employees = frappe.get_all(


        "Employee",


        pluck="name"

    )




    rank = 1




    for emp in employees:



        kpi = frappe.db.get_value(


            "Employee KPI",


            {

                "employee":

                    emp

            },


            [


                "average_evaluation_score",

                "total_calls",

                "converted_leads"

            ],


            as_dict=True

        )




        if not kpi:

            continue




        lb = frappe.db.exists(



            "Counselor Leaderboard",



            {

                "employee":

                    emp

            }

        )




        if not lb:



            doc = frappe.get_doc({



                "doctype":

                    "Counselor Leaderboard",



                "employee":

                    emp



            })


            doc.insert(


                ignore_permissions=True

            )


            lb = doc.name




        lb = frappe.get_doc(

            "Counselor Leaderboard",

            lb

        )




        lb.score = (

            kpi.average_evaluation_score

            or 0

        )




        lb.total_calls = (

            kpi.total_calls

            or 0

        )




        lb.closed = (

            kpi.converted_leads

            or 0

        )




        lb.rank = rank




        lb.save()



        rank += 1




    frappe.db.commit()

