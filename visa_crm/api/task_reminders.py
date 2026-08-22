# Copyright (c) 2026, Shahbaz and contributors
# For license information, please see license.txt

import datetime
import frappe
from frappe.utils import get_datetime, add_days


@frappe.whitelist()
def send_task_due_reminders():
	"""
	Scans active CRM Tasks and generates reminder notifications for assigned employees
	based on task due dates. Enforces idempotency and prevents duplicates.
	"""
	try:
		now = frappe.utils.now_datetime()
	except Exception:
		now = datetime.datetime.now()

	# Scan tasks due up to 24 hours in the future or overdue within last 7 days
	window_start = add_days(now, -7)
	window_end = add_days(now, 1)

	tasks = frappe.db.sql("""
		SELECT name, title, priority, due_date, assigned_to, owner,
		       reference_doctype, reference_docname, status
		FROM `tabCRM Task`
		WHERE status NOT IN ('Done', 'Canceled')
		  AND assigned_to IS NOT NULL
		  AND assigned_to != ''
		  AND assigned_to != 'Administrator'
		  AND due_date IS NOT NULL
		  AND due_date >= %(start)s
		  AND due_date <= %(end)s
	""", {"start": window_start, "end": window_end}, as_dict=True)

	created_count = 0
	for task in tasks:
		if not frappe.db.exists("User", task.assigned_to):
			continue

		due_dt = get_datetime(task.due_date)
		due_date_str = due_dt.strftime("%Y-%m-%d")
		formatted_due = due_dt.strftime("%b %d, %Y %I:%M %p")
		task_id = str(task.name)

		# Idempotency check: notification for this task and this due date already sent to this user
		existing_notif = frappe.db.sql("""
			SELECT name FROM `tabCRM Notification`
			WHERE notification_type_doctype = 'CRM Task'
			  AND notification_type_doc = %(task_id)s
			  AND to_user = %(user)s
			  AND message LIKE %(due_pat)s
			LIMIT 1
		""", {
			"task_id": task_id,
			"user": task.assigned_to,
			"due_pat": f"%Due: {due_date_str}%"
		})

		if existing_notif:
			continue

		# Reference details
		ref_title = ""
		if task.reference_doctype == "CRM Lead" and task.reference_docname:
			ref_title = frappe.db.get_value("CRM Lead", task.reference_docname, "lead_name") or task.reference_docname
		elif task.reference_doctype == "CRM Deal" and task.reference_docname:
			ref_title = frappe.db.get_value("CRM Deal", task.reference_docname, "organization") or task.reference_docname

		notif_text = f"""
			<div class="mb-2 leading-5 text-ink-gray-5">
				<span class="font-medium text-ink-gray-9">Task Reminder:</span>
				<span> { task.title }</span>
				{ f' for <span class="font-medium text-ink-gray-9">{ ref_title }</span>' if ref_title else '' }
				<span> is due on </span>
				<span class="font-medium text-amber-600">{ formatted_due }</span>
			</div>
		"""

		message = f"Task Due: {task.title} (Due: {due_date_str})"

		notif = frappe.new_doc("CRM Notification")
		notif.from_user = task.owner or task.assigned_to
		notif.to_user = task.assigned_to
		notif.type = "Task"
		notif.message = message
		notif.notification_text = notif_text
		notif.notification_type_doctype = "CRM Task"
		notif.notification_type_doc = task_id
		notif.reference_doctype = task.reference_doctype or "CRM Lead"
		notif.reference_name = task.reference_docname or ""
		notif.read = 0
		notif.insert(ignore_permissions=True)
		created_count += 1

	return {"ok": True, "reminders_sent": created_count, "tasks_evaluated": len(tasks)}


def on_task_update(doc, method=None):
	"""
	Hook called when a CRM Task is updated:
	- If marked 'Done' or 'Canceled', mark all unread reminder notifications for this task as read.
	- If unassigned, clear notifications for previous assignee.
	"""
	task_id = str(doc.name)
	if doc.status in ("Done", "Canceled"):
		frappe.db.sql("""
			UPDATE `tabCRM Notification`
			SET `read` = 1
			WHERE notification_type_doctype = 'CRM Task'
			  AND notification_type_doc = %(task_id)s
			  AND `read` = 0
		""", {"task_id": task_id})
