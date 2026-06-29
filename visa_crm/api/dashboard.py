import frappe

@frappe.whitelist()
def manager_kpis():
    return{
    "customers":frappe.db.count("Customer"),
    "leads":frappe.db.count("CRM Lead"),
    "calls":frappe.db.count("Call Intelligence"),
    "communication_events":frappe.db.count("Communication Event"),
    "todos":frappe.db.count("ToDo",{"status":"Open"}),
    "hot_leads":frappe.db.count("Lead Score History",{"score":[">=",80]}),
    "medium_leads":frappe.db.count("Lead Score History",{"score":["between",[40,79]]}),
    "cold_leads":frappe.db.count("Lead Score History",{"score":["<",40]})
    }