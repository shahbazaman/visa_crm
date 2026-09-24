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
    """
    try:
        frappe.reload_doc("visa_crm", "doctype", "appointment_letter_template")
        frappe.reload_doc("visa_crm", "doctype", "employee_appointment_letter")
    except Exception as e:
        frappe.log_error(f"setup_appointment_letters reload error: {e}", "setup_appointment_letters")

    setup_appointment_letter_templates()
    setup_default_print_format()
    frappe.db.commit()
    print("[setup_appointment_letters] Middle East Travels and Holidays appointment letter templates initialized.")
