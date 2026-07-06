import frappe

from visa_crm.api.customer_matcher import match_customer
from visa_crm.api.lead_creator import create_lead
from visa_crm.api.lead_assignment import assign_employee
from visa_crm.api.todo_creator import create_followup
from visa_crm.api.workflow_manager import update_workflow


def process_pending():

    queues=frappe.get_all(
        "Lead Intake Queue",
        filters={
            "status":"Lead Received"
        },
        pluck="name"
    )

    for queue_name in queues:
        process_queue(queue_name)


def process_queue(queue_name):

    queue=frappe.get_doc("Lead Intake Queue",queue_name)

    existing=match_customer(queue)

    if existing:
        queue.status="Processed"
        queue.matched_lead=existing
        queue.save(ignore_permissions=True)
        frappe.db.commit()
        return

    lead=create_lead(queue)

    assign_employee(lead)

    update_workflow(lead)

    create_followup(lead)

    queue.status="Processed"
    queue.matched_lead=lead.name
    queue.save(ignore_permissions=True)

    frappe.db.commit()