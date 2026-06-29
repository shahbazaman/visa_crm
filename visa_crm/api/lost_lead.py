import frappe


def generate_reason(ci):

    txt=(ci.summary or "").lower()


    reason="Other"


    if "budget" in txt:
        reason="Price"

    elif "document" in txt:
        reason="Documents Missing"

    elif "competitor" in txt:
        reason="Competitor"

    elif "reject" in txt:
        reason="Visa Rejected"




    doc=frappe.new_doc(
        "Lost Lead Reason"
    )



    doc.lead=ci.lead_match

    doc.employee=ci.employee_match

    doc.reason=reason

    doc.insert(
        ignore_permissions=True
    )



    return reason