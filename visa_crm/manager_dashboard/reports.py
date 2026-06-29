import frappe

def employee_report(employee):

    return frappe.get_all(

        "Employee KPI",

        filters={

            "employee":employee

        },

        fields=["*"]

    )

def call_report():

    return frappe.get_all(

        "Call Intelligence",

        fields=["*"]

    )

def lead_report():

    return frappe.get_all(

        "CRM Lead",

        fields=["*"]

    )

