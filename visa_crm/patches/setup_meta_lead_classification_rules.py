import frappe

RULES = [
    ("WhatsApp to Reservation", 10, "WhatsApp", "Source", "Equals", "WhatsApp", "Reservation", "WhatsApp inquiry"),
    ("Meta Visa Campaign", 100, "Meta", "Campaign Name", "Ends With", "visa", "Global Visa", "Meta campaign ends with visa"),
    ("Meta Package Campaign", 110, "Meta", "Campaign Name", "Ends With", "package", "Holidays", "Meta campaign ends with package"),
    ("Meta Holiday Campaign Suffix", 120, "Meta", "Campaign Name", "Ends With", "campaign", "Holidays", "Meta campaign ends with campaign"),
    ("Meta Holiday Campign Suffix", 121, "Meta", "Campaign Name", "Ends With", "campign", "Holidays", "Meta campaign ends with campign"),
    ("Meta Holiday Leads Suffix", 122, "Meta", "Campaign Name", "Ends With", "leads", "Holidays", "Meta campaign ends with leads"),
]


def execute():
    if not frappe.db.exists("DocType", "Lead Classification Rule"):
        return
    for name, priority, source, field, match_type, value, category, reason in RULES:
        values = {
            "rule_name": name,
            "priority": priority,
            "source_channel": source,
            "match_field": field,
            "match_type": match_type,
            "match_value": value,
            "category": category,
            "reason": reason,
            "enabled": 1,
        }
        if frappe.db.exists("Lead Classification Rule", name):
            frappe.db.set_value("Lead Classification Rule", name, values, update_modified=False)
        else:
            frappe.get_doc({"doctype": "Lead Classification Rule", **values}).insert(ignore_permissions=True)
    frappe.clear_cache(doctype="Lead Classification Rule")
    frappe.db.commit()
