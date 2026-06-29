import frappe




def send_reminders():



    todos=frappe.get_all(

        "ToDo",


        filters={

            "status":"Open"

        },


        fields=[

            "name",

            "allocated_to",

            "description"

        ]

    )



    for d in todos:



        frappe.log_error(

            title="REMINDER",


            message=f"""

{d.allocated_to}



{d.description}

"""

        )