import frappe
from frappe.utils import add_days




def create_followup(ci):



    if ci.followup_created:
        return



    todo=frappe.new_doc(
        "ToDo"
    )


    todo.description=f"""

Call customer

{ci.customer_name}


Visa

{ci.visa_type}


Intent

{ci.lead_intent}

"""


    todo.date=add_days(

        frappe.utils.today(),

        1

    )


    todo.insert()



    ci.followup_created=1

    ci.followup_reference=todo.name


    ci.save()