import unittest
from unittest.mock import patch
import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api import notification_services

class TestNotificationStatus(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.patcher = patch("frappe.enqueue", return_value=None)
        self.patcher.start()
        self.test_user = frappe.session.user
        self.notif_doc = frappe.get_doc({
            "doctype": "Notification Log",
            "subject": "Test Notification Read Status",
            "email_content": "This is a test notification content",
            "for_user": self.test_user,
            "type": "Alert",
            "read": 0
        }).insert(ignore_permissions=True)

    def tearDown(self):
        self.patcher.stop()
        if frappe.db.exists("Notification Log", self.notif_doc.name):
            frappe.db.delete("Notification Log", {"name": self.notif_doc.name})
            frappe.db.commit()
        super().tearDown()

    def test_get_user_notifications_filtering(self):
        unread_res = notification_services.get_user_notifications(status="unread")
        self.assertTrue(unread_res.get("ok"))
        unread_ids = [n["id"] for n in unread_res.get("notifications", [])]
        self.assertIn(self.notif_doc.name, unread_ids)

    def test_mark_as_read_and_unread(self):
        # 1. Mark as Read
        res_read = notification_services.mark_notification_as_read(self.notif_doc.name)
        self.assertTrue(res_read.get("ok"))
        self.assertEqual(frappe.db.get_value("Notification Log", self.notif_doc.name, "read"), 1)

        # 2. Mark as Unread
        res_unread = notification_services.mark_notification_as_unread(self.notif_doc.name)
        self.assertTrue(res_unread.get("ok"))
        self.assertEqual(frappe.db.get_value("Notification Log", self.notif_doc.name, "read"), 0)

    def test_toggle_read_status(self):
        # Initial is 0 -> toggle -> 1
        res1 = notification_services.toggle_read_status(self.notif_doc.name)
        self.assertEqual(res1.get("read"), 1)
        self.assertEqual(frappe.db.get_value("Notification Log", self.notif_doc.name, "read"), 1)

        # Toggle again -> 0
        res2 = notification_services.toggle_read_status(self.notif_doc.name)
        self.assertEqual(res2.get("read"), 0)
        self.assertEqual(frappe.db.get_value("Notification Log", self.notif_doc.name, "read"), 0)

    def test_mark_all_read(self):
        res = notification_services.mark_all_read(user=self.test_user)
        self.assertTrue(res.get("ok"))
        self.assertEqual(frappe.db.get_value("Notification Log", self.notif_doc.name, "read"), 1)
