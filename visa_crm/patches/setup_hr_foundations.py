# -*- coding: utf-8 -*-
"""
Idempotent Setup Patch for Visa CRM HR Architecture
====================================================
Configures:
1. Custom Fields on Employee (Probation, Aadhaar, Holiday Assignments, Documents)
2. Property Setters (notice period hiding)
3. Salary Component (ESI and Special Allowance)
4. Role assignment (Employee role for staff users)
5. User Permissions (linking 9 production employees to their accounts)
6. Workflows for Leave Application and Attendance Request
"""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

def execute():
    for step_name, fn in [
        ("custom_fields", setup_custom_fields),
        ("property_setters", setup_property_setters),
        ("salary_components", setup_salary_components),
        ("link_employees", link_production_employees),
        ("workflows", setup_workflows),
        ("offer_letter_template", setup_offer_letter_template),
        ("letter_head", setup_letter_head),
        ("default_print_format", setup_default_print_format),
    ]:
        try:
            fn()
            print(f"[setup_hr_foundations] Step {step_name} completed.")
        except Exception as e:
            print(f"[setup_hr_foundations] Step {step_name} non-fatal warning: {e}")
            frappe.log_error(f"setup_hr_foundations step {step_name} warning: {e}", "setup_hr_foundations")

def setup_custom_fields():
    custom_fields = {
        "Employee": [
            {
                "fieldname": "custom_probation_end_date",
                "label": "Probation End Date",
                "fieldtype": "Date",
                "insert_after": "custom_is_on_probation",
                "description": "Expected or confirmed end date of probation period"
            },
            {
                "fieldname": "custom_probation_status",
                "label": "Probation Status",
                "fieldtype": "Select",
                "options": "Pending\nConfirmed\nExtended",
                "default": "Pending",
                "insert_after": "custom_probation_end_date"
            },
            {
                "fieldname": "custom_aadhaar_number",
                "label": "Aadhaar Number",
                "fieldtype": "Data",
                "insert_after": "pan_number",
                "description": "12-digit Indian UIDAI Aadhaar Number"
            },
            {
                "fieldname": "custom_holiday_assignments",
                "label": "Holiday Assignments",
                "fieldtype": "Table",
                "options": "Employee Holiday Assignment",
                "insert_after": "holiday_list",
                "description": "Multiple effective-dated holiday lists merged deterministically"
            },
            {
                "fieldname": "custom_employee_documents",
                "label": "Employee Documents",
                "fieldtype": "Table",
                "options": "Employee Document",
                "insert_after": "profile_tab",
                "description": "Verified employee certificates, identity, and compliance documents"
            }
        ],
        "Attendance Request": [
            {
                "fieldname": "custom_check_in",
                "label": "Requested Check-In Time",
                "fieldtype": "Time",
                "insert_after": "shift"
            },
            {
                "fieldname": "custom_check_out",
                "label": "Requested Check-Out Time",
                "fieldtype": "Time",
                "insert_after": "custom_check_in"
            },
            {
                "fieldname": "custom_hr_remarks",
                "label": "HR Remarks",
                "fieldtype": "Small Text",
                "insert_after": "explanation"
            }
        ]
    }
    create_custom_fields(custom_fields, ignore_validate=True)
    frappe.clear_cache(doctype="Employee")
    frappe.clear_cache(doctype="Attendance Request")

def setup_property_setters():
    # Ensure notice_number_of_days is hidden
    if not frappe.db.exists("Property Setter", "Employee-notice_number_of_days-hidden"):
        make_property_setter("Employee", "notice_number_of_days", "hidden", 1, "Check")

def setup_salary_components():
    # 1. ESI (Deduction)
    if not frappe.db.exists("Salary Component", "ESI"):
        esi = frappe.new_doc("Salary Component")
        esi.salary_component = "ESI"
        esi.salary_component_abbr = "ESI"
        esi.type = "Deduction"
        esi.description = "Employee State Insurance (0.75% of Gross if Gross <= Rs. 21,000)"
        esi.depends_on_payment_days = 1
        esi.is_tax_applicable = 0
        esi.condition = "gross_pay <= 21000"
        esi.formula = "gross_pay * 0.0075"
        esi.flags.ignore_permissions = True
        esi.insert()

    # 2. Special Allowance (Earning)
    if not frappe.db.exists("Salary Component", "Special Allowance"):
        sa = frappe.new_doc("Salary Component")
        sa.salary_component = "Special Allowance"
        sa.salary_component_abbr = "SA"
        sa.type = "Earning"
        sa.description = "Balancing Special Allowance"
        sa.depends_on_payment_days = 1
        sa.is_tax_applicable = 1
        sa.flags.ignore_permissions = True
        sa.insert()

def link_production_employees():
    """
    Connects production employee records to their respective system users
    and ensures standard Employee role and User Permissions exist.
    """
    email_map = {
        "HR-EMP-00001": "princyjithin11@gmail.com",
        "HR-EMP-00002": "risvanriz08@gmail.com",
        "HR-EMP-00003": "bdm@middleeasttravels.in",
        "HR-EMP-00004": "ticketsmett@middleeasttravels.in",
        "HR-EMP-00005": "nairaswathi02@gmail.com",
        "HR-EMP-00006": "mufisantorian@gmail.com",
        "HR-EMP-00007": "rahimanmettccj@gmail.com",
        "HR-EMP-00008": "akhilpn9037@gmail.com",
        "HR-EMP-00009": "hakeekathussiraja@gmail.com",
    }

    for emp_id, email in email_map.items():
        if frappe.db.exists("Employee", emp_id) and frappe.db.exists("User", email):
            # Update user_id on Employee
            current_user = frappe.db.get_value("Employee", emp_id, "user_id")
            if current_user != email:
                frappe.db.set_value("Employee", emp_id, "user_id", email)

            # Ensure Employee role on User
            user_doc = frappe.get_doc("User", email)
            existing_roles = [r.role for r in user_doc.roles]
            if "Employee" not in existing_roles:
                user_doc.append("roles", {"role": "Employee"})
                user_doc.flags.ignore_permissions = True
                user_doc.save()

            # Ensure User Permission exists
            if not frappe.db.exists("User Permission", {"user": email, "allow": "Employee", "for_value": emp_id}):
                up = frappe.new_doc("User Permission")
                up.user = email
                up.allow = "Employee"
                up.for_value = emp_id
                up.is_default = 1
                up.flags.ignore_permissions = True
                up.insert()

def setup_workflows():
    try:
        if not frappe.db.exists("DocType", "Leave Application"):
            return
        if not frappe.db.exists("Workflow", "Leave Application Workflow"):
            for s in ["Draft", "Pending Approval", "Approved", "Rejected"]:
                if not frappe.db.exists("Workflow State", s):
                    ws = frappe.new_doc("Workflow State")
                    ws.workflow_state_name = s
                    ws.flags.ignore_permissions = True
                    ws.insert()

            for act in ["Submit for Approval", "Approve", "Reject"]:
                if not frappe.db.exists("Workflow Action Master", act):
                    wa = frappe.new_doc("Workflow Action Master")
                    wa.workflow_action_name = act
                    wa.flags.ignore_permissions = True
                    wa.insert()

            for r in ["Employee", "HR User", "HR Manager", "Leave Approver"]:
                if not frappe.db.exists("Role", r):
                    return

            wf = frappe.new_doc("Workflow")
            wf.workflow_name = "Leave Application Workflow"
            wf.document_type = "Leave Application"
            wf.is_active = 0
            wf.workflow_state_field = "workflow_state"

            wf.set("states", [
                {"state": "Draft", "doc_status": "0", "allow_edit": "Employee"},
                {"state": "Pending Approval", "doc_status": "0", "allow_edit": "HR User"},
                {"state": "Approved", "doc_status": "1", "allow_edit": "HR Manager"},
                {"state": "Rejected", "doc_status": "0", "allow_edit": "HR Manager"}
            ])

            wf.set("transitions", [
                {
                    "state": "Draft",
                    "action": "Submit for Approval",
                    "next_state": "Pending Approval",
                    "allowed": "Employee"
                },
                {
                    "state": "Pending Approval",
                    "action": "Approve",
                    "next_state": "Approved",
                    "allowed": "Leave Approver"
                },
                {
                    "state": "Pending Approval",
                    "action": "Reject",
                    "next_state": "Rejected",
                    "allowed": "Leave Approver"
                }
            ])
            wf.flags.ignore_permissions = True
            wf.insert()
    except Exception as e:
        print(f"setup_workflows skipped: {e}")

def setup_offer_letter_template():
    if not frappe.db.exists("DocType", "Offer Letter Template"):
        return
    tmpl_name = "Middle East Travels Default Offer Letter Template"
    if not frappe.db.exists("Offer Letter Template", tmpl_name):
        comp = "middle east holidays" if frappe.db.exists("Company", "middle east holidays") else (frappe.db.get_single_value("Global Defaults", "default_company") or "")
        tmpl = frappe.new_doc("Offer Letter Template")
        tmpl.template_name = tmpl_name
        tmpl.is_default = 1
        tmpl.company = comp
        tmpl.company_name_display = "Middle East Travels & Tourism"
        tmpl.heading = "CONGRATULATIONS"
        tmpl.subject_prefix = "Offer of Employment – "
        tmpl.salutation_template = "Dear Mr./Ms. {first_name},"
        tmpl.introduction = "With reference to the discussions we had with you, we are pleased to extend to you an offer for the position of Sales & Marketing Executive at Middle East Travels & Tourism. We are delighted to have you join our organization and look forward to your valuable contribution to the Company. The terms and conditions of this offer are detailed below:"
        tmpl.compensation_text = "Your monthly salary will be INR {monthly_salary} ({monthly_salary_in_words}).<br>All deductions as per company policy and applicable government regulations shall apply."
        tmpl.probation_text = "You will be on probation for a period of {probation_period} from the date of joining. Upon successful completion of the probation period and subject to satisfactory performance, you shall be confirmed through a letter to this effect, issued by the HR Dept. The Company reserves the right to extend the probation period or not confirm your employment if your performance is found unsatisfactory."
        tmpl.performance_review_text = "Your performance will be reviewed periodically as per company policy. Salary increments and incentives, if any, shall be at the sole discretion of the management and will be based on your performance, results achieved, and the overall performance of the company."
        tmpl.working_hours_text = "Your working hours will be from {working_hours}."
        tmpl.leave_text = "You will be entitled to two (2) paid leaves per month, in accordance with company policy. During probation, you will be entitled to only one (1) paid leave per month."
        tmpl.notice_period_text = "Either party may terminate the employment by providing one (1) month’s written notice or salary in lieu thereof, in accordance with company policy. The Company reserves the right to relieve the employee earlier or waive the notice period at its discretion. In special cases, management has the privilege to decide the notice period duration."
        tmpl.joining_details_text = "You are requested to report at Middle East Travels & Tourism on {joining_date_formatted} at {joining_time} to complete the joining formalities. A detailed appointment letter will be issued upon joining."
        tmpl.required_documents_text = "<ol><li>Relieving letter and experience certificates from present and previous employers</li><li>Last three months’ salary slips or salary certificate from your current employer</li><li>Certificates of educational qualifications</li><li>Aadhaar Card</li><li>PAN Card</li><li>Two Passport-size photograph</li><li>Bank proof</li></ol>"
        tmpl.acceptance_text = "This offer is subject to your acceptance of the terms and conditions stated herein. Please confirm your acceptance by signing and returning a copy of this letter by email within 24 hours. Upon receipt of your acceptance, this offer shall be deemed binding on both parties."
        tmpl.acceptance_statement = "I accept the offer of employment with the terms and conditions as mentioned in the offer letter."
        tmpl.signatory_company_label = "For, Middle East Travels & Tourism"
        tmpl.default_hr_signatory_name = "Gopika"
        tmpl.default_hr_signatory_designation = "HR Consultant"
        tmpl.default_hr_signatory_title = "Authorized Signatory"
        tmpl.footer_address = "Shobha Tower, 5/3412L, Mavoor Rd, near Emerald Mall, Arayidathupalam, Kozhikode, Kerala 673004"
        tmpl.footer_contact = "Tel: 91 8593944666,91 7025144666"
        tmpl.footer_email_web = "info@middleeasttravels.in | www.middleeasttravels.in"
        tmpl.flags.ignore_permissions = True
        tmpl.insert()
        print("Seeded default Offer Letter Template")

def setup_letter_head():
    lh_name = "Middle East Travels & Tourism"
    if not frappe.db.exists("Letter Head", lh_name):
        lh = frappe.new_doc("Letter Head")
        lh.letter_head_name = lh_name
        lh.is_default = 1
        lh.content = """<div style="display: flex; justify-content: space-between; align-items: center; padding-bottom: 12px; border-bottom: 1px solid #1f2937;">
  <div style="display: flex; flex-direction: column;">
    <span style="font-family: 'Montserrat', sans-serif; font-size: 22px; font-weight: 900; color: #000; letter-spacing: 0.5px;">MIDDLE EAST</span>
    <span style="font-family: 'Montserrat', sans-serif; font-size: 8px; font-weight: 700; color: #000; letter-spacing: 3.5px; text-transform: uppercase;">TRAVELS & TOURISM</span>
  </div>
  <div>
    <svg style="width: 55px; height: 38px;" viewBox="0 0 100 70" xmlns="http://www.w3.org/2000/svg">
      <circle cx="50" cy="35" r="30" fill="#005a9c" />
      <ellipse cx="50" cy="35" rx="28" ry="12" fill="none" stroke="#ffffff" stroke-width="1.8" />
      <ellipse cx="50" cy="35" rx="14" ry="28" fill="none" stroke="#ffffff" stroke-width="1.8" />
      <line x1="20" y1="35" x2="80" y2="35" stroke="#ffffff" stroke-width="1.8" />
      <rect x="22" y="24" width="56" height="22" rx="4" fill="#005a9c" opacity="0.95" />
      <text x="50" y="41" font-family="sans-serif" font-size="16" font-weight="900" fill="#ffffff" text-anchor="middle" letter-spacing="1">IATA</text>
    </svg>
  </div>
</div>"""
        lh.footer = """<div style="width: 100%; border-top: 1px solid #1f2937; padding-top: 8px; text-align: center; font-size: 10px; line-height: 1.45; color: #374151;">
  <div style="font-weight: 500; color: #1f2937;">Shobha Tower, 5/3412L, Mavoor Rd, near Emerald Mall, Arayidathupalam, Kozhikode, Kerala 673004</div>
  <div style="margin-top: 2px;">Tel: 91 8593944666, 91 7025144666</div>
  <div style="margin-top: 2px; color: #4b5563;">info@middleeasttravels.in | www.middleeasttravels.in</div>
</div>"""
        lh.flags.ignore_permissions = True
        lh.insert()
        print("Seeded Middle East Travels & Tourism Letter Head")

def setup_default_print_format():
    try:
        if frappe.db.exists("Print Format", "Middle East Travels Offer Letter"):
            frappe.db.set_value("Print Format", "Middle East Travels Offer Letter", "default", 1)
            frappe.db.set_value("Print Format", "Middle East Travels Offer Letter", "disabled", 0)
        if frappe.db.exists("DocType", "Employee Offer Letter"):
            frappe.db.set_value("DocType", "Employee Offer Letter", "default_print_format", "Middle East Travels Offer Letter")
        frappe.db.commit()
        print("Enforced Middle East Travels Offer Letter as system default print format!")
    except Exception as e:
        print(f"setup_default_print_format warning: {e}")
