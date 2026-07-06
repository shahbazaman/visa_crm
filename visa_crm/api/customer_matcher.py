import frappe

def find_customer(phone):

    if not phone:
        return None


    return frappe.db.get_value(

        "Customer",

        {"mobile_no":phone},

        "name"

    )




def find_lead(phone):

    if not phone:
        return None


    return frappe.db.get_value(

        "CRM Lead",

        {"mobile_no":phone},

        "name"

    )





def find_employee(phone):


    if not phone:
        return None


    return frappe.db.get_value(

        "Employee",

        {"cell_number":phone},

        "name"

    )




def match_all(phone):



    return {


        "customer":

            find_customer(phone),


        "lead":

            find_lead(phone),


        "employee":

            find_employee(phone)


    }


def match_customer(queue):

    if queue.phone:

        lead=frappe.db.exists(
            "Lead",
            {"mobile_no":queue.phone}
        )

        if lead:
            return lead

    if queue.email:

        lead=frappe.db.exists(
            "Lead",
            {"email_id":queue.email}
        )

        if lead:
            return lead

    return None
