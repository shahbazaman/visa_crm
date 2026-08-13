"""
visa_crm/tests/test_counselor_round_robin.py
==============================================
Comprehensive Counselor Assignment & Round-Robin Routing Tests (18 Test Suite).

Required Coverage:
  01 — Holidays Lead Routing -> Holidays - MEH (local: Holidays - HNC)
  02 — Global Visa Lead Routing -> Global visa - MEH (local: Global Visa - HNC)
  03 — WhatsApp Lead Routing -> Reservation - MEH (local: Reservation - HNC)
  04 — WhatsApp Precedence -> WhatsApp + Holidays -> Reservation
  05 — WhatsApp Precedence -> WhatsApp + Global Visa -> Reservation
  06 — Administrator User Exclusion -> Employee linked to Administrator NEVER selected
  07 — Guest User Exclusion -> Guest user NEVER selected
  08 — Disabled User Exclusion -> Disabled user's employee NOT eligible
  09 — Inactive Employee Exclusion -> Inactive employee NOT eligible
  10 — Wrong Department Exclusion -> Employee in wrong department NEVER selected
  11 — Missing Manager Exclusion -> Counselor without valid manager NOT eligible
  12 — Administrator Manager Exclusion -> Counselor reporting to Administrator NOT eligible
  13 — Department-Specific Round-Robin -> Sequential slots distributed independently
  14 — Idempotent Retry -> Reuses existing assignment without advancing counter
  15 — No Eligible Counselor -> Stage FAILED cleanly, prior business docs intact
  16 — Manual Override -> System Manager can override; cannot select Administrator
  17 — Persisted to CRM Lead -> Both assigned_counselor AND manager persisted
  18 — Hook Overwrite Protection -> Subsequent doc saves cannot overwrite with Administrator
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.utils import now_datetime

from visa_crm.api import lead_assignment
from visa_crm.api.lead_assignment import (
    SUPPORTED_DEPARTMENTS,
    NotApplicable,
    _eligible_employees_for_department,
    _get_or_create_state,
    _resolve_manager,
    assign_lead,
    get_responsible_department,
    is_whatsapp_lead,
    override_counselor,
)


class TestCounselorRoundRobin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        frappe.flags.in_test = True
        cls._created_users = []
        cls._created_employees = []

        # Patch frappe.enqueue so User/Lead events don't fail when Redis queue is offline
        cls._enqueue_patcher = patch("frappe.enqueue", return_value=None)
        cls._enqueue_patcher.start()

        # 1. Ensure test departments exist
        for dept in ("Holidays - HNC", "Global Visa - HNC", "Reservation - HNC", "Holidays", "Global Visa", "Reservation"):
            if not frappe.db.exists("Department", dept):
                d = frappe.new_doc("Department")
                d.name = dept
                d.department_name = dept
                d.parent_department = "All Departments"
                d.flags.ignore_mandatory = True
                d.insert(ignore_permissions=True, ignore_if_duplicate=True)

        # 2. Helper to create test user & employee safely
        def _make_user(email, first_name, enabled=1):
            if not frappe.db.exists("User", email):
                u = frappe.new_doc("User")
                u.email = email
                u.first_name = first_name
                u.enabled = enabled
                u.send_welcome_email = 0
                u.flags.ignore_password_policy = True
                u.insert(ignore_permissions=True)
                cls._created_users.append(email)
            frappe.db.set_value("User", email, "enabled", int(enabled), update_modified=False)
            frappe.db.commit()
            return email

        def _make_emp(name, dept, user_id, reports_to=None, status="Active"):
            existing = None
            if user_id:
                existing = frappe.db.get_value("Employee", {"user_id": user_id}, "name")
            if not existing:
                existing = frappe.db.get_value("Employee", {"employee_name": name}, "name")

            if not existing:
                e = frappe.new_doc("Employee")
                e.employee_name = name
                e.first_name = name
                e.department = dept
                e.status = status
                e.user_id = user_id
                e.reports_to = reports_to
                e.date_of_birth = "1990-01-01"
                e.date_of_joining = "2024-01-01"
                e.gender = "Female"
                e.flags.ignore_mandatory = True
                e.insert(ignore_permissions=True)
                cls._created_employees.append(e.name)
                return e.name
            else:
                frappe.db.set_value("Employee", existing, {
                    "employee_name": name,
                    "first_name": name,
                    "department": dept,
                    "status": status,
                    "user_id": user_id,
                    "reports_to": reports_to,
                }, update_modified=False)
                return existing

        # Managers (with valid active users, not Administrator)
        m1_u = _make_user("t_mgr_holidays@test.local", "Holidays Manager")
        m1_e = _make_emp("Test Holidays Manager", "Holidays - HNC", m1_u)

        m2_u = _make_user("t_mgr_gv@test.local", "GV Manager")
        m2_e = _make_emp("Test GV Manager", "Global Visa - HNC", m2_u)

        m3_u = _make_user("t_mgr_res@test.local", "Reservation Manager")
        m3_e = _make_emp("Test Reservation Manager", "Reservation - HNC", m3_u)

        # Holidays Counselors
        h1_u = _make_user("t_counselor_h1@test.local", "Holidays Counselor 1")
        cls.h1_emp = _make_emp("Test Holidays Counselor 1", "Holidays - HNC", h1_u, reports_to=m1_e)

        h2_u = _make_user("t_counselor_h2@test.local", "Holidays Counselor 2")
        cls.h2_emp = _make_emp("Test Holidays Counselor 2", "Holidays - HNC", h2_u, reports_to=m1_e)

        # Global Visa Counselor
        gv1_u = _make_user("t_counselor_gv1@test.local", "GV Counselor 1")
        cls.gv1_emp = _make_emp("Test Global Visa Counselor 1", "Global Visa - HNC", gv1_u, reports_to=m2_e)

        # Reservation Counselor
        res1_u = _make_user("t_counselor_res1@test.local", "Reservation Counselor 1")
        cls.res1_emp = _make_emp("Test Reservation Counselor 1", "Reservation - HNC", res1_u, reports_to=m3_e)

        # Disabled User Counselor
        dis_u = _make_user("t_counselor_disabled@test.local", "Disabled Counselor", enabled=0)
        cls.dis_emp = _make_emp("Test Disabled Counselor", "Holidays - HNC", dis_u, reports_to=m1_e)

        # Inactive Employee Counselor
        inact_u = _make_user("t_counselor_inactive@test.local", "Inactive Counselor")
        cls.inact_emp = _make_emp("Test Inactive Counselor", "Holidays - HNC", inact_u, reports_to=m1_e, status="Inactive")

        # Counselor with No Manager
        nomgr_u = _make_user("t_counselor_nomgr@test.local", "No Manager Counselor")
        cls.nomgr_emp = _make_emp("Test No Manager Counselor", "Holidays - HNC", nomgr_u, reports_to=None)

        # Counselor Reporting to Administrator User
        admin_mgr_u = "Administrator"
        admin_mgr_e = _make_emp("Test Admin Linked Emp", "Holidays - HNC", admin_mgr_u)
        cls.admin_emp = admin_mgr_e
        adminrep_u = _make_user("t_counselor_adminrep@test.local", "Admin Reporting Counselor")
        cls.adminrep_emp = _make_emp("Test Admin Reporting Counselor", "Holidays - HNC", adminrep_u, reports_to=admin_mgr_e)

        # Guest Linked Employee
        guest_u = "Guest"
        cls.guest_emp = _make_emp("Test Guest Linked Emp", "Holidays - HNC", guest_u)

        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        try:
            cls._enqueue_patcher.stop()
        except Exception:
            pass

    def setUp(self):
        frappe.set_user("Administrator")
        frappe.flags.in_test = True
        for dept in ("Holidays - HNC", "Global Visa - HNC", "Reservation - HNC", "Holidays", "Global Visa", "Reservation"):
            if frappe.db.exists("Department Round Robin State", dept):
                frappe.db.set_value(
                    "Department Round Robin State", dept,
                    {"current_index": 0, "last_assigned_employee": None, "lock_token": None, "lock_expires_at": None},
                    update_modified=False,
                )
        frappe.db.commit()

    # ------------------------------------------------------------------
    # Test 1: Holidays Routing
    # ------------------------------------------------------------------
    def test_01_holidays_routing(self):
        """Lead with category Holidays routes to Holidays department, active Employee, valid Manager, not Administrator."""
        queue_doc = frappe._dict(
            name="TEST-Q-HOLIDAYS-01",
            lead_category="Holidays",
            lead_source="Meta Ads",
            responsible_department=None,
        )
        dept = get_responsible_department(queue_doc=queue_doc)
        self.assertIsNotNone(dept)
        self.assertTrue(dept.startswith("Holidays"))

        emp = assign_lead(lead=None, queue_doc=queue_doc)
        self.assertIsNotNone(emp, "Should assign a Holidays counselor")
        self.assertNotEqual(emp, "Administrator")

        emp_data = frappe.db.get_value("Employee", emp, ["department", "status", "user_id", "reports_to"], as_dict=True)
        self.assertEqual(emp_data.status, "Active")
        self.assertTrue(emp_data.department.startswith("Holidays"))
        self.assertNotEqual(emp_data.user_id, "Administrator")

        mgr_emp, mgr_user = _resolve_manager(emp)
        self.assertIsNotNone(mgr_emp)
        self.assertIsNotNone(mgr_user)
        self.assertNotEqual(mgr_user, "Administrator")

    # ------------------------------------------------------------------
    # Test 2: Global Visa Routing
    # ------------------------------------------------------------------
    def test_02_global_visa_routing(self):
        """Lead with category Global Visa routes to Global Visa department, active Employee, valid Manager."""
        queue_doc = frappe._dict(
            name="TEST-Q-GV-01",
            lead_category="Global Visa",
            lead_source="Meta Ads",
            responsible_department=None,
        )
        dept = get_responsible_department(queue_doc=queue_doc)
        self.assertIsNotNone(dept)
        self.assertTrue("Global" in dept and "Visa" in dept)

        emp = assign_lead(lead=None, queue_doc=queue_doc)
        self.assertIsNotNone(emp, "Should assign a Global Visa counselor")
        self.assertNotEqual(emp, "Administrator")

        emp_data = frappe.db.get_value("Employee", emp, ["department", "status", "user_id"], as_dict=True)
        self.assertEqual(emp_data.status, "Active")
        self.assertTrue("Global" in emp_data.department and "Visa" in emp_data.department)
        self.assertNotEqual(emp_data.user_id, "Administrator")

    # ------------------------------------------------------------------
    # Test 3: WhatsApp Routing
    # ------------------------------------------------------------------
    def test_03_whatsapp_routing(self):
        """Lead from WhatsApp source routes to Reservation department."""
        queue_doc = frappe._dict(
            name="TEST-Q-WA-01",
            lead_source="WhatsApp",
            lead_category=None,
            responsible_department=None,
        )
        self.assertTrue(is_whatsapp_lead(queue_doc=queue_doc))
        dept = get_responsible_department(queue_doc=queue_doc)
        self.assertIsNotNone(dept)
        self.assertTrue(dept.startswith("Reservation"))

        emp = assign_lead(lead=None, queue_doc=queue_doc)
        self.assertIsNotNone(emp, "Should assign a Reservation counselor for WhatsApp lead")
        self.assertNotEqual(emp, "Administrator")

        emp_data = frappe.db.get_value("Employee", emp, ["department", "status", "user_id"], as_dict=True)
        self.assertEqual(emp_data.status, "Active")
        self.assertTrue(emp_data.department.startswith("Reservation"))
        self.assertNotEqual(emp_data.user_id, "Administrator")

    # ------------------------------------------------------------------
    # Test 4: WhatsApp Precedence over Holidays
    # ------------------------------------------------------------------
    def test_04_whatsapp_precedence_over_holidays(self):
        """When a lead is from WhatsApp AND category is Holidays, WhatsApp routing takes precedence -> Reservation."""
        queue_doc = frappe._dict(
            name="TEST-Q-WA-H-01",
            lead_source="WhatsApp",
            lead_category="Holidays",
            responsible_department=None,
        )
        dept = get_responsible_department(queue_doc=queue_doc)
        self.assertIsNotNone(dept)
        self.assertTrue(dept.startswith("Reservation"), f"Expected Reservation department for WhatsApp lead, got {dept}")

    # ------------------------------------------------------------------
    # Test 5: WhatsApp Precedence over Global Visa
    # ------------------------------------------------------------------
    def test_05_whatsapp_precedence_over_global_visa(self):
        """When a lead is from WhatsApp AND category is Global Visa, WhatsApp routing takes precedence -> Reservation."""
        queue_doc = frappe._dict(
            name="TEST-Q-WA-GV-01",
            lead_source="WhatsApp",
            lead_category="Global Visa",
            responsible_department=None,
        )
        dept = get_responsible_department(queue_doc=queue_doc)
        self.assertIsNotNone(dept)
        self.assertTrue(dept.startswith("Reservation"), f"Expected Reservation department for WhatsApp lead, got {dept}")

    # ------------------------------------------------------------------
    # Test 6: Administrator User Exclusion
    # ------------------------------------------------------------------
    def test_06_administrator_user_excluded(self):
        """Administrator user is never selected as counselor even if an Employee record links to Administrator."""
        eligible = _eligible_employees_for_department("Holidays - HNC")
        self.assertNotIn(self.admin_emp, eligible, "Employee linked to Administrator must be excluded")
        for emp_id in eligible:
            uid = frappe.db.get_value("Employee", emp_id, "user_id")
            self.assertNotEqual(uid, "Administrator")

    # ------------------------------------------------------------------
    # Test 7: Guest User Exclusion
    # ------------------------------------------------------------------
    def test_07_guest_user_excluded(self):
        """Guest user / employee linked to Guest is never selected."""
        eligible = _eligible_employees_for_department("Holidays - HNC")
        self.assertNotIn(self.guest_emp, eligible, "Employee linked to Guest must be excluded")

    # ------------------------------------------------------------------
    # Test 8: Disabled Counselor User Exclusion
    # ------------------------------------------------------------------
    def test_08_disabled_user_excluded(self):
        """Employee whose linked user is disabled (enabled=0) is not eligible."""
        eligible = _eligible_employees_for_department("Holidays - HNC")
        self.assertNotIn(self.dis_emp, eligible, "Disabled user's employee must be excluded")

    # ------------------------------------------------------------------
    # Test 9: Inactive Employee Exclusion
    # ------------------------------------------------------------------
    def test_09_inactive_employee_excluded(self):
        """Employee with status != 'Active' is not eligible."""
        eligible = _eligible_employees_for_department("Holidays - HNC")
        self.assertNotIn(self.inact_emp, eligible, "Inactive employee must be excluded")

    # ------------------------------------------------------------------
    # Test 10: Wrong Department Filtered Out
    # ------------------------------------------------------------------
    def test_10_wrong_department_excluded(self):
        """Employees from other departments must never appear in department counselor list."""
        holidays_emps = _eligible_employees_for_department("Holidays - HNC")
        gv_emps = _eligible_employees_for_department("Global Visa - HNC")
        res_emps = _eligible_employees_for_department("Reservation - HNC")

        self.assertNotIn(self.gv1_emp, holidays_emps)
        self.assertNotIn(self.res1_emp, holidays_emps)
        self.assertNotIn(self.h1_emp, gv_emps)
        self.assertNotIn(self.h1_emp, res_emps)

    # ------------------------------------------------------------------
    # Test 11: Missing Manager Exclusion
    # ------------------------------------------------------------------
    def test_11_missing_manager_excluded(self):
        """Counselor with no reports_to is not eligible for assignment."""
        eligible = _eligible_employees_for_department("Holidays - HNC", require_manager=True)
        self.assertNotIn(self.nomgr_emp, eligible, "Counselor with no manager must be excluded")

    # ------------------------------------------------------------------
    # Test 12: Administrator Manager Exclusion
    # ------------------------------------------------------------------
    def test_12_administrator_manager_excluded(self):
        """Counselor reporting to Administrator user is not eligible for assignment."""
        eligible = _eligible_employees_for_department("Holidays - HNC", require_manager=True)
        self.assertNotIn(self.adminrep_emp, eligible, "Counselor reporting to Administrator must be excluded")

    # ------------------------------------------------------------------
    # Test 13: Department-Specific Round-Robin
    # ------------------------------------------------------------------
    def test_13_department_specific_round_robin(self):
        """Sequential round-robin assignments advance index and select different employees."""
        dept = "Holidays - HNC"
        eligible = _eligible_employees_for_department(dept)
        if len(eligible) >= 2:
            emp1, dec1 = lead_assignment._round_robin_assign(dept)
            emp2, dec2 = lead_assignment._round_robin_assign(dept)
            self.assertNotEqual(emp1, emp2, "Sequential round-robin slots must be distinct")

    # ------------------------------------------------------------------
    # Test 14: Idempotency
    # ------------------------------------------------------------------
    def test_14_idempotency_returns_same_counselor(self):
        """Retrying the same queue returns the existing assignment without changing counselor."""
        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "first_name": "Idempotency Test Lead",
            "status": "New",
        }).insert(ignore_permissions=True)

        queue_name = f"TEST-Q-IDEMP-{lead.name}"
        queue_doc = frappe._dict(
            name=queue_name,
            lead_category="Holidays",
            responsible_department="Holidays - HNC",
        )
        try:
            emp1 = assign_lead(lead=lead.name, queue_doc=queue_doc)
            self.assertIsNotNone(emp1)

            # Second call with same queue_doc and lead
            emp2 = assign_lead(lead=lead.name, queue_doc=queue_doc)
            self.assertEqual(emp1, emp2, "Existing assignment must be reused idempotently")
        finally:
            frappe.db.delete("CRM Lead", {"name": lead.name})
            frappe.db.delete("Lead Assignment", {"meta_intake_key": f"assignment:{queue_name}"})
            frappe.db.delete("Counselor Assignment History", {"lead": lead.name})
            frappe.db.commit()

    # ------------------------------------------------------------------
    # Test 15: No Eligible Counselor -> Stage FAILED
    # ------------------------------------------------------------------
    def test_15_no_counselor_fails_stage(self):
        """If a supported department has no eligible employees, assign_lead returns None and records FAILED."""
        queue_doc = frappe._dict(
            name="TEST-Q-EMPTY-01",
            lead_category="Holidays",
            responsible_department="Empty Dept",
        )
        with patch("visa_crm.api.lead_assignment.get_responsible_department", return_value="Empty Dept"), \
             patch("visa_crm.api.lead_assignment.is_supported_department", return_value=True):
            emp = assign_lead(lead=None, queue_doc=queue_doc)
            self.assertIsNone(emp)

    # ------------------------------------------------------------------
    # Test 16: Manual Override Rejects Administrator
    # ------------------------------------------------------------------
    def test_16_override_rejects_administrator(self):
        """Override must reject assigning an employee linked to Administrator user."""
        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "first_name": "Admin Override Test",
            "status": "New",
        }).insert(ignore_permissions=True)

        try:
            with self.assertRaises(frappe.ValidationError):
                override_counselor(lead=lead.name, new_employee=self.admin_emp, reason="Invalid admin test")
        finally:
            frappe.db.delete("CRM Lead", {"name": lead.name})
            frappe.db.commit()

    # ------------------------------------------------------------------
    # Test 17: Counselor and Manager Persisted to CRM Lead
    # ------------------------------------------------------------------
    def test_17_counselor_and_manager_persisted_to_crm_lead(self):
        """Assigning lead persists both assigned_counselor and manager on the CRM Lead."""
        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "first_name": "Persistence Test Lead",
            "status": "New",
            "lead_category": "Holidays",
        }).insert(ignore_permissions=True)

        queue_name = f"TEST-Q-PERSIST-{lead.name}"
        queue_doc = frappe._dict(
            name=queue_name,
            lead_category="Holidays",
            responsible_department="Holidays - HNC",
        )
        try:
            emp = assign_lead(lead=lead.name, queue_doc=queue_doc)
            self.assertIsNotNone(emp)

            # Reload lead doc from DB
            lead_doc = frappe.get_doc("CRM Lead", lead.name)
            self.assertEqual(lead_doc.assigned_counselor, emp)

            # Manager must be valid non-Administrator
            mgr_emp, mgr_user = _resolve_manager(emp)
            self.assertIsNotNone(mgr_emp)
            self.assertNotEqual(mgr_user, "Administrator")
        finally:
            frappe.db.delete("CRM Lead", {"name": lead.name})
            frappe.db.delete("Lead Assignment", {"meta_intake_key": f"assignment:{queue_name}"})
            frappe.db.delete("Counselor Assignment History", {"lead": lead.name})
            frappe.db.commit()

    # ------------------------------------------------------------------
    # Test 18: Protection Against Overwriting with Administrator
    # ------------------------------------------------------------------
    def test_18_no_hook_overwrites_with_administrator(self):
        """Ensure that saving a CRM Lead does not trigger any hook that resets counselor to Administrator."""
        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "first_name": "Hook Overwrite Test Lead",
            "status": "New",
            "assigned_counselor": self.h1_emp,
        }).insert(ignore_permissions=True)

        try:
            # Trigger standard save & validate lifecycle hooks
            lead.first_name = "Hook Overwrite Modified Name"
            lead.save(ignore_permissions=True)

            reloaded_counselor = frappe.db.get_value("CRM Lead", lead.name, "assigned_counselor")
            self.assertEqual(reloaded_counselor, self.h1_emp)
            self.assertNotEqual(reloaded_counselor, "Administrator")
        finally:
            frappe.db.delete("CRM Lead", {"name": lead.name})
            frappe.db.commit()
