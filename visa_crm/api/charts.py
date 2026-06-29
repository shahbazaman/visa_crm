import frappe

@frappe.whitelist()
def sentiment_chart():
    data=frappe.db.sql("""
    select sentiment,count(*)
    from `tabCommunication Event`
    group by sentiment
    """,as_dict=True)
    return data

@frappe.whitelist()
def employee_chart():
    data=frappe.db.sql("""
    select employee,avg(overall_score) score
    from `tabEmployee Evaluation`
    group by employee
    order by score desc
    """,as_dict=True)
    return data

@frappe.whitelist()
def lead_score_chart():
    data=frappe.db.sql("""
    select date(avg(creation)) day,avg(score) score
    from `tabLead Score History`
    group by date(creation)
    order by day
    """,as_dict=True)
    return data