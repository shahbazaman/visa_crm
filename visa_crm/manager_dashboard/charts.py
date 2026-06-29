import frappe
def daily_calls():

    return frappe.db.sql("""

    select

    date(creation),

    count(*)

    from `tabCall Intelligence`

    group by date(creation)

    order by date(creation)

    """)

def daily_leads():

    return frappe.db.sql("""

    select

    date(creation),

    count(*)

    from `tabCRM Lead`

    group by date(creation)

    order by date(creation)

    """)

def employee_ranking():

    return frappe.db.sql("""

    select

    employee,

    avg(score)

    from `tabEmployee KPI`

    group by employee

    order by avg(score) desc

    """)

def lead_conversion():

    return frappe.db.sql("""

    select

    status,

    count(*)

    from `tabCRM Lead`

    group by status

    """)

def lost_reasons():

    return frappe.db.sql("""

    select

    lost_reason,

    count(*)

    from `tabLost Lead Intelligence`

    group by lost_reason

    """)

def sentiment():

    return frappe.db.sql("""

    select

    sentiment,

    count(*)

    from `tabCall Intelligence`

    group by sentiment

    """)

