def assign_employee(lead):

    lead.custom_assigned_employee="Administrator"

    lead.save(ignore_permissions=True)