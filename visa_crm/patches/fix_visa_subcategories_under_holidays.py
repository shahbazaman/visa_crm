import frappe
from visa_crm.api.lead_classification import is_visa_suffix, category_department, ensure_lead_subcategory


def execute():
    """
    Migration patch to:
    1. Move any CRM Lead and Lead Intake Queue records under Holidays ending with 'visa' to Global Visa.
    2. Reassign/reuse existing Global Visa subcategories (e.g. UK Tourist Visa, UK Family Visit Visa, UK Business Visa).
    3. Clean up any duplicate/orphaned subcategories under Holidays ending with 'visa'.
    4. Idempotent and safe for repeated runs.
    """
    global_visa_dept = category_department("Global Visa") or "Global visa - MEH"

    # 1. Migrate affected CRM Leads
    crm_leads = frappe.get_all(
        "CRM Lead",
        filters={"lead_category": "Holidays"},
        fields=["name", "lead_group"]
    )
    migrated_leads = 0
    for lead in crm_leads:
        grp = lead.get("lead_group")
        if is_visa_suffix(grp):
            # Ensure subcategory exists under Global Visa
            ensure_lead_subcategory("Global Visa", grp)
            frappe.db.set_value(
                "CRM Lead",
                lead.name,
                {
                    "lead_category": "Global Visa",
                    "responsible_department": global_visa_dept,
                    "classification_reason": f"Visa subcategory '{grp}' migrated from Holidays to Global Visa",
                },
                update_modified=False,
            )
            migrated_leads += 1

    # 2. Migrate affected Lead Intake Queues
    queues = frappe.get_all(
        "Lead Intake Queue",
        filters={"lead_category": "Holidays"},
        fields=["name", "lead_group"]
    )
    migrated_queues = 0
    for q in queues:
        grp = q.get("lead_group")
        if is_visa_suffix(grp):
            ensure_lead_subcategory("Global Visa", grp)
            frappe.db.set_value(
                "Lead Intake Queue",
                q.name,
                {
                    "lead_category": "Global Visa",
                    "responsible_department": global_visa_dept,
                    "classification_reason": f"Visa subcategory '{grp}' migrated from Holidays to Global Visa",
                },
                update_modified=False,
            )
            migrated_queues += 1

    # 3. Clean up duplicate subcategories under Holidays ending with 'visa'
    if frappe.db.exists("DocType", "Lead Subcategory"):
        holidays_subs = frappe.get_all(
            "Lead Subcategory",
            filters={"parent_category": "Holidays"},
            fields=["name", "sub_category_name"]
        )
        for sub in holidays_subs:
            s_name = sub.get("sub_category_name")
            if is_visa_suffix(s_name):
                clean_name = str(s_name).strip()
                # Check if it already exists under Global Visa
                gv_exists = frappe.db.exists(
                    "Lead Subcategory",
                    {"parent_category": "Global Visa", "sub_category_name": clean_name}
                )
                if not gv_exists:
                    # Move to Global Visa
                    frappe.db.set_value("Lead Subcategory", sub.name, "parent_category", "Global Visa", update_modified=False)
                else:
                    # Global Visa record already exists; safely delete the Holidays duplicate
                    frappe.delete_doc("Lead Subcategory", sub.name, ignore_permissions=True, force=True)

    frappe.clear_cache(doctype="Lead Subcategory")
    frappe.clear_cache(doctype="CRM Lead")
    frappe.clear_cache(doctype="Lead Intake Queue")
    frappe.db.commit()
