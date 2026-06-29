import frappe




def update_employee_kpi(

        employee

):



    kpi = frappe.db.exists(


        "Employee KPI",

        {

            "employee":

                employee

        }

    )




    if not kpi:



        doc = frappe.get_doc({


            "doctype":

                "Employee KPI",



            "employee":

                employee


        })


        doc.insert(


            ignore_permissions=True

        )



        kpi = doc.name




    kpi = frappe.get_doc(

        "Employee KPI",

        kpi

    )




    evaluations = frappe.get_all(



        "Employee Evaluation",



        filters={


            "employee":

                employee

        },



        fields=[


            "overall_score"

        ]


    )




    total = len(


        evaluations

    )



    avg = 0



    if total:


        avg = sum(

            [

                x.overall_score

                for x in evaluations

            ]

        ) / total




    kpi.average_evaluation_score = avg



    kpi.total_calls = frappe.db.count(


        "Communication Event",


        {

            "employee":

                employee

        }


    )



    kpi.save()



    frappe.db.commit()

