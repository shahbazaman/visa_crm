import frappe
from visa_crm.api.communication_center import send_message

class NotificationService:
    channel = "System"
    def send(self, to, subject, message, **kwargs):
        raise NotImplementedError

class WhatsAppNotification(NotificationService):
    channel = "WhatsApp"
    def send(self, to, subject, message, **kwargs):
        return send_message("whatsapp", to, message, **kwargs)

class EmailNotification(NotificationService):
    channel = "Email"
    def send(self, to, subject, message, **kwargs):
        frappe.sendmail(recipients=[to], subject=subject, message=message, now=False)
        return {"ok": True, "channel": self.channel}

class SystemNotification(NotificationService):
    channel = "System"
    def send(self, to, subject, message, **kwargs):
        doc = frappe.new_doc("Notification Log")
        doc.subject = subject
        doc.email_content = message
        doc.for_user = to
        doc.type = "Alert"
        doc.read = 0
        if kwargs.get("document_type"):
            doc.document_type = kwargs.get("document_type")
        if kwargs.get("document_name"):
            doc.document_name = kwargs.get("document_name")
        doc.insert(ignore_permissions=True)
        return {"ok": True, "channel": self.channel, "name": doc.name}

class PushNotification(NotificationService):
    channel = "Push"
    def send(self, to, subject, message, **kwargs):
        return {"ok": False, "channel": self.channel, "reason": "Push provider not configured"}

SERVICES = {
    "whatsapp": WhatsAppNotification,
    "email": EmailNotification,
    "system": SystemNotification,
    "push": PushNotification
}

def notify(channel, to, subject, message, **kwargs):
    return SERVICES.get((channel or "system").lower(), SystemNotification)().send(to, subject, message, **kwargs)


# ============================================================================
# NOTIFICATION READ / UNREAD MANAGEMENT (Frappe CRM & Framework)
# ============================================================================

@frappe.whitelist()
def get_user_notifications(status="all", limit=50):
    """
    Returns notifications for the current user with support for status filtering:
    - 'all': All notifications
    - 'unread': Only unread notifications (read == 0)
    - 'read': Only read notifications (read == 1)
    """
    user = frappe.session.user
    limit = max(int(limit or 50), 1)

    # 1. Query Frappe Framework 'Notification Log'
    filters = {"for_user": user}
    if status == "unread":
        filters["read"] = 0
    elif status == "read":
        filters["read"] = 1

    logs = frappe.get_all(
        "Notification Log",
        filters=filters,
        fields=["name", "subject", "email_content", "type", "read", "creation", "document_type", "document_name", "from_user"],
        order_by="creation desc",
        limit_page_length=limit
    )

    # 2. Also query CRM-specific 'CRM Notification' if it exists
    crm_notifs = []
    if frappe.db.exists("DocType", "CRM Notification"):
        crm_filters = {"to_user": user}
        if status == "unread":
            crm_filters["read"] = 0
        elif status == "read":
            crm_filters["read"] = 1
        crm_notifs = frappe.get_all(
            "CRM Notification",
            filters=crm_filters,
            fields=["name", "notification_text", "type", "read", "creation", "reference_doctype", "reference_name", "from_user"],
            order_by="creation desc",
            limit_page_length=limit
        )

    # Normalize output format
    results = []
    for l in logs:
        results.append({
            "id": l.name,
            "doctype": "Notification Log",
            "title": l.subject,
            "message": l.email_content,
            "type": l.type,
            "read": bool(l.read),
            "status": "Read" if l.read else "Unread",
            "created_at": str(l.creation),
            "reference_doctype": l.document_type,
            "reference_name": l.document_name,
            "from_user": l.from_user
        })

    for c in crm_notifs:
        results.append({
            "id": c.name,
            "doctype": "CRM Notification",
            "title": c.notification_text,
            "message": c.notification_text,
            "type": c.type,
            "read": bool(c.read),
            "status": "Read" if c.read else "Unread",
            "created_at": str(c.creation),
            "reference_doctype": c.reference_doctype,
            "reference_name": c.reference_name,
            "from_user": c.from_user
        })

    # Sort combined by creation date descending
    results.sort(key=lambda x: x["created_at"], reverse=True)
    return {
        "ok": True,
        "status_filter": status,
        "unread_count": sum(1 for r in results if not r["read"]),
        "notifications": results[:limit]
    }


@frappe.whitelist()
def mark_notification_as_read(notification_name, doctype=None):
    """Marks a specific notification as Read."""
    if not notification_name:
        return {"ok": False, "error": "notification_name required"}

    dt = doctype or ("CRM Notification" if frappe.db.exists("CRM Notification", notification_name) else "Notification Log")
    if frappe.db.exists(dt, notification_name):
        frappe.db.set_value(dt, notification_name, "read", 1, update_modified=False)
        frappe.db.commit()
        return {"ok": True, "name": notification_name, "read": 1, "status": "Read"}
    return {"ok": False, "error": f"{dt} {notification_name} not found"}


@frappe.whitelist()
def mark_notification_as_unread(notification_name, doctype=None):
    """Marks a specific notification as Unread."""
    if not notification_name:
        return {"ok": False, "error": "notification_name required"}

    dt = doctype or ("CRM Notification" if frappe.db.exists("CRM Notification", notification_name) else "Notification Log")
    if frappe.db.exists(dt, notification_name):
        frappe.db.set_value(dt, notification_name, "read", 0, update_modified=False)
        frappe.db.commit()
        return {"ok": True, "name": notification_name, "read": 0, "status": "Unread"}
    return {"ok": False, "error": f"{dt} {notification_name} not found"}


@frappe.whitelist()
def toggle_read_status(notification_name, doctype=None):
    """Toggles read/unread status for a given notification."""
    if not notification_name:
        return {"ok": False, "error": "notification_name required"}

    dt = doctype or ("CRM Notification" if frappe.db.exists("CRM Notification", notification_name) else "Notification Log")
    if frappe.db.exists(dt, notification_name):
        current = frappe.db.get_value(dt, notification_name, "read")
        new_val = 0 if current else 1
        frappe.db.set_value(dt, notification_name, "read", new_val, update_modified=False)
        frappe.db.commit()
        return {"ok": True, "name": notification_name, "read": new_val, "status": "Read" if new_val else "Unread"}
    return {"ok": False, "error": f"{dt} {notification_name} not found"}


@frappe.whitelist()
def mark_all_read(user=None):
    """Marks all unread notifications for the user as Read."""
    user = user or frappe.session.user
    count_logs = 0
    count_crm = 0

    if frappe.db.exists("DocType", "Notification Log"):
        frappe.db.sql("""update `tabNotification Log` set `read`=1 where `for_user`=%s and `read`=0""", (user,))
        count_logs = frappe.db._cursor.rowcount

    if frappe.db.exists("DocType", "CRM Notification"):
        frappe.db.sql("""update `tabCRM Notification` set `read`=1 where `to_user`=%s and `read`=0""", (user,))
        count_crm = frappe.db._cursor.rowcount

    frappe.db.commit()
    return {"ok": True, "user": user, "marked_read": count_logs + count_crm}
