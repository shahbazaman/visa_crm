import frappe

def build_dashboard():

    return{

        "overview":overview(),

        "employees":employee_summary(),

        "calls":call_summary(),

        "leads":lead_summary(),

        "customers":customer_summary(),

        "followups":followup_summary()

    }

def overview():

    return {

        "employees":frappe.db.count("Employee"),

        "customers":frappe.db.count("Customer"),

        "calls":frappe.db.count("Call Intelligence"),

        "leads":frappe.db.count("CRM Lead"),

        "positive_calls":frappe.db.count(
            "Call Intelligence",
            {"sentiment":"Positive"}
        ),

        "negative_calls":frappe.db.count(
            "Call Intelligence",
            {"sentiment":"Negative"}
        ),

        "pending_followups":frappe.db.count(
            "ToDo",
            {"status":"Open"}
        )

    }

def employee_summary():

    return frappe.db.sql("""

    SELECT

        employee,

        total_calls,

        total_leads,

        converted_leads,

        average_lead_score,

        average_evaluation_score,

        pending_followups,

        positive_calls,

        neutral_calls,

        negative_calls

    FROM `tabEmployee KPI`

    ORDER BY average_evaluation_score DESC,
             converted_leads DESC,
             total_calls DESC

    LIMIT 10

    """,as_dict=True)

def call_summary():

    return frappe.db.sql("""

    select

    sentiment,

    count(*) total

    from `tabCall Intelligence`

    group by sentiment

    """,as_dict=True)

def lead_summary():

    return frappe.db.sql("""

    select

    lead_intent,

    count(*) total

    from `tabCall Intelligence`

    group by lead_intent

    """,as_dict=True)

def customer_summary():

    return frappe.db.sql("""

    select

    customer_360_match,

    count(*) total

    from `tabCall Intelligence`

    where customer_360_match is not null

    group by customer_360_match

    """,as_dict=True)

def followup_summary():

    return frappe.db.sql("""

    select

    status,

    count(*) total

    from `tabToDo`

    group by status

    """,as_dict=True)

