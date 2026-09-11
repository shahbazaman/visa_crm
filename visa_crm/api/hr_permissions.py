# -*- coding: utf-8 -*-
"""
HR Permission Security Engine for Visa CRM
===========================================
Ensures strict server-side database level filtering:
1. Normal employees only see their own records.
2. Managers see their own and their direct reports' records.
3. HR User and HR Manager can view and manage all records.
"""
import frappe

def is_hr_or_manager(user=None):
    if not user:
        user = frappe.session.user
    if user in ["Administrator", "admin@middleeast.com"]:
        return True
    roles = frappe.get_roles(user)
    return any(r in roles for r in ["System Manager", "HR Manager", "HR User"])

def get_employee_scope(user=None):
    """
    Returns (employee_id, list_of_direct_report_employee_ids)
    """
    if not user:
        user = frappe.session.user
    emp = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
    if not emp:
        # Check by email
        emp = frappe.db.get_value("Employee", {"company_email": user, "status": "Active"}, "name")
    if not emp:
        emp = frappe.db.get_value("Employee", {"personal_email": user, "status": "Active"}, "name")

    if not emp:
        return None, []

    reports = frappe.get_all("Employee", filters={"reports_to": emp, "status": "Active"}, pluck="name")
    return emp, reports

def attendance_permission_query(user=None):
    if is_hr_or_manager(user):
        return ""
    emp, reports = get_employee_scope(user)
    if not emp:
        return "1=0"
    allowed = [emp] + reports
    allowed_str = ", ".join([frappe.db.escape(x) for x in allowed])
    return f"`tabAttendance`.`employee` in ({allowed_str})"

def leave_application_permission_query(user=None):
    if is_hr_or_manager(user):
        return ""
    emp, reports = get_employee_scope(user)
    if not emp:
        return "1=0"
    allowed = [emp] + reports
    allowed_str = ", ".join([frappe.db.escape(x) for x in allowed])
    return f"`tabLeave Application`.`employee` in ({allowed_str})"

def attendance_request_permission_query(user=None):
    if is_hr_or_manager(user):
        return ""
    emp, reports = get_employee_scope(user)
    if not emp:
        return "1=0"
    allowed = [emp] + reports
    allowed_str = ", ".join([frappe.db.escape(x) for x in allowed])
    return f"`tabAttendance Request`.`employee` in ({allowed_str})"

def salary_slip_permission_query(user=None):
    if is_hr_or_manager(user):
        return ""
    emp, _ = get_employee_scope(user)
    if not emp:
        return "1=0"
    return f"`tabSalary Slip`.`employee` = {frappe.db.escape(emp)}"

def employee_letter_permission_query(user=None):
    if is_hr_or_manager(user):
        return ""
    emp, _ = get_employee_scope(user)
    if not emp:
        return "1=0"
    # Employees can only view their own letters once issued
    return f"`tabEmployee Letter`.`employee` = {frappe.db.escape(emp)} and `tabEmployee Letter`.`status` = 'Issued'"

def attendance_has_permission(doc, ptype="read", user=None):
    if is_hr_or_manager(user):
        return True
    emp, reports = get_employee_scope(user)
    if not emp:
        return False
    if ptype in ["write", "create", "delete", "submit", "cancel"]:
        return False  # Normal employees cannot write finalized Attendance!
    return doc.employee in ([emp] + reports)

def leave_application_has_permission(doc, ptype="read", user=None):
    if is_hr_or_manager(user):
        return True
    emp, reports = get_employee_scope(user)
    if not emp:
        return False
    if doc.employee == emp:
        return True
    if doc.employee in reports and ptype in ["read", "write"]:
        return True
    return False

def salary_slip_has_permission(doc, ptype="read", user=None):
    if is_hr_or_manager(user):
        return True
    emp, _ = get_employee_scope(user)
    if not emp:
        return False
    if ptype != "read":
        return False
    return doc.employee == emp

def employee_letter_has_permission(doc, ptype="read", user=None):
    if is_hr_or_manager(user):
        return True
    emp, _ = get_employee_scope(user)
    if not emp:
        return False
    if ptype != "read":
        return False
    return doc.employee == emp and doc.status == "Issued"

def employee_offer_letter_permission_query(user=None):
    if is_hr_or_manager(user):
        return ""
    emp, _ = get_employee_scope(user)
    if not emp:
        return "1=0"
    return f"`tabEmployee Offer Letter`.`employee` = {frappe.db.escape(emp)} and `tabEmployee Offer Letter`.`status` = 'Issued'"

def employee_offer_letter_has_permission(doc, ptype="read", user=None):
    if is_hr_or_manager(user):
        return True
    emp, _ = get_employee_scope(user)
    if not emp:
        return False
    if ptype != "read":
        return False
    return doc.employee == emp and doc.status == "Issued"

def offer_letter_template_permission_query(user=None):
    if is_hr_or_manager(user):
        return ""
    return "1=0"

def offer_letter_template_has_permission(doc, ptype="read", user=None):
    return is_hr_or_manager(user)
