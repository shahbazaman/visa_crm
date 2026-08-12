import frappe
import json


def execute():
    # 1. Ensure Property Setter for label and read_only on meta_campaign_name
    if frappe.db.exists("DocType", "CRM Lead"):
        ps_label = frappe.db.exists(
            "Property Setter",
            {"doc_type": "CRM Lead", "field_name": "meta_campaign_name", "property": "label"},
        )
        if not ps_label:
            frappe.get_doc({
                "doctype": "Property Setter",
                "doc_type": "CRM Lead",
                "doctype_or_field": "DocField",
                "field_name": "meta_campaign_name",
                "property": "label",
                "property_type": "Data",
                "value": "Campaign Name",
            }).insert(ignore_permissions=True)
        else:
            frappe.db.set_value("Property Setter", ps_label, "value", "Campaign Name")

        ps_ro = frappe.db.exists(
            "Property Setter",
            {"doc_type": "CRM Lead", "field_name": "meta_campaign_name", "property": "read_only"},
        )
        if not ps_ro:
            frappe.get_doc({
                "doctype": "Property Setter",
                "doc_type": "CRM Lead",
                "doctype_or_field": "DocField",
                "field_name": "meta_campaign_name",
                "property": "read_only",
                "property_type": "Check",
                "value": "1",
            }).insert(ignore_permissions=True)
        else:
            frappe.db.set_value("Property Setter", ps_ro, "value", "1")

    # 2. Update CRM Fields Layout sidepanel for CRM Lead
    if frappe.db.exists("CRM Fields Layout", {"dt": "CRM Lead", "type": "Side Panel"}):
        doc = frappe.get_doc("CRM Fields Layout", {"dt": "CRM Lead", "type": "Side Panel"})
        layout = json.loads(doc.layout or "[]")
        for section in layout:
            if section.get("name") in ("details_section", "Details") or section.get("label") == "Details":
                for col in section.get("columns") or []:
                    fields = col.get("fields") or []
                    if "meta_campaign_name" not in fields:
                        if "source" in fields:
                            idx = fields.index("source")
                            fields.insert(idx + 1, "meta_campaign_name")
                        elif "lead_owner" in fields:
                            idx = fields.index("lead_owner")
                            fields.insert(idx, "meta_campaign_name")
                        else:
                            fields.append("meta_campaign_name")
                        col["fields"] = fields
        doc.layout = json.dumps(layout)
        doc.save(ignore_permissions=True)
        frappe.db.commit()
