# -*- coding: utf-8 -*-
import frappe
from visa_crm.patches.setup_hr_foundations import (
    setup_appointment_letter_templates,
    setup_default_print_format,
)

def execute():
    """
    Setup Appointment Letter Templates and default print formats for
    Middle East Travels & Tourism and Middle East Holidays.
    Supports both standard HRMS 'Appointment Letter' and 'Employee Appointment Letter'.
    """
    try:
        if frappe.db.exists("DocType", "Appointment Letter Template"):
            frappe.reload_doc("visa_crm", "doctype", "appointment_letter_template")
        if frappe.db.exists("DocType", "Employee Appointment Letter"):
            frappe.reload_doc("visa_crm", "doctype", "employee_appointment_letter")
    except Exception as e:
        frappe.log_error(f"setup_appointment_letters reload error: {e}", "setup_appointment_letters")

    # Reload all 4 Print Formats
    for pf in [
        "middle_east_travels_appointment_letter",
        "middle_east_holidays_appointment_letter",
        "employee_travels_appointment_letter",
        "employee_holidays_appointment_letter",
    ]:
        try:
            frappe.reload_doc("visa_crm", "print_format", pf)
        except Exception as e:
            print(f"Non-fatal reload print format {pf}: {e}")

    # Seed templates (supports both HRMS terms table and visa_crm fields)
    setup_appointment_letter_templates()

    # Enforce default print formats
    enforce_appointment_letter_print_formats()

    frappe.db.commit()
    print("[setup_appointment_letters] Middle East Travels & Holidays appointment letters initialized successfully.")

def enforce_appointment_letter_print_formats():
    # 1. Standard HRMS Appointment Letter
    try:
        if frappe.db.exists("Print Format", "Middle East Travels Appointment Letter"):
            frappe.db.set_value("Print Format", "Middle East Travels Appointment Letter", "default", 1)
            frappe.db.set_value("Print Format", "Middle East Travels Appointment Letter", "disabled", 0)
        if frappe.db.exists("DocType", "Appointment Letter"):
            frappe.db.set_value("DocType", "Appointment Letter", "default_print_format", "Middle East Travels Appointment Letter")
            print("Set default print format on Appointment Letter to Middle East Travels Appointment Letter")
    except Exception as e:
        print(f"Warning setting Appointment Letter default print format: {e}")

    # 2. Employee Appointment Letter (visa_crm)
    try:
        if frappe.db.exists("Print Format", "Employee Travels Appointment Letter"):
            frappe.db.set_value("Print Format", "Employee Travels Appointment Letter", "default", 1)
            frappe.db.set_value("Print Format", "Employee Travels Appointment Letter", "disabled", 0)
        if frappe.db.exists("DocType", "Employee Appointment Letter"):
            frappe.db.set_value("DocType", "Employee Appointment Letter", "default_print_format", "Employee Travels Appointment Letter")
            print("Set default print format on Employee Appointment Letter to Employee Travels Appointment Letter")
    except Exception as e:
        print(f"Warning setting Employee Appointment Letter default print format: {e}")
