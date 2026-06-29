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

        "leads":frappe.db.count("CRM Lead")

    }

def employee_summary():

    return frappe.db.sql("""

    select

    employee,

    avg(score) score,

    avg(conversion_rate) conversion,

    avg(response_time) response

    from `tabEmployee KPI`

    group by employee

    order by score desc

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

