def update_workflow(lead):

    lead.status="Open"

    lead.save(ignore_permissions=True)