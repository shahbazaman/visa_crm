import frappe


def create_lost_lead(lead):

    if frappe.db.exists(
        "Lost Lead Intelligence",
        {"lead":lead.name}
    ):
        return


    doc=frappe.new_doc(
        "Lost Lead Intelligence"
    )

    doc.lead=lead.name
    doc.employee=lead.owner

    doc.lead_score=lead.lead_score

    doc.country=lead.country
    doc.visa_type=lead.visa_type

    doc.reason="Other"

    doc.insert(
        ignore_permissions=True
    )