import frappe
from frappe.utils import today

def create_reminders():
    todos=frappe.get_all("ToDo",filters={"status":"Open"},fields=["name","date"])
    for t in todos:
        if not t.date:
            continue
        if str(t.date)==today():
            frappe.publish_realtime("todo_reminder",{"todo":t.name})