import frappe
from visa_crm.api.meta_utils import has_doctype, has_field

@frappe.whitelist()
def sentiment_chart():
    _staff()
    if not has_doctype("Communication Event") or not has_field("Communication Event","sentiment"):
        return []
    data=frappe.db.sql("""
    select sentiment,count(*)
    from `tabCommunication Event`
    group by sentiment
    """,as_dict=True)
    return data

@frappe.whitelist()
def employee_chart():
    _staff()
    if not has_doctype("Employee Evaluation") or not has_field("Employee Evaluation","employee") or not has_field("Employee Evaluation","overall_score"):
        return []
    data=frappe.db.sql("""
    select employee,avg(overall_score) score
    from `tabEmployee Evaluation`
    group by employee
    order by score desc
    """,as_dict=True)
    return data

@frappe.whitelist()
def lead_score_chart():
    _staff()
    if not has_doctype("Lead Score History") or not has_field("Lead Score History","score"):
        return []
    data=frappe.db.sql("""
    select date(avg(creation)) day,avg(score) score
    from `tabLead Score History`
    group by date(creation)
    order by day
    """,as_dict=True)
    return data

def _staff():
    if frappe.session.user=="Guest" or not ({"System Manager","Sales Manager","Counselor","Visa Processing","Administrator"} & set(frappe.get_roles())):
        frappe.throw("Visa CRM staff access required", frappe.PermissionError)
