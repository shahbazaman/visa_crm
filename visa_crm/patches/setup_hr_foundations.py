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
        ("appointment_letter_templates", setup_appointment_letter_templates),
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

def setup_appointment_letter_templates():
    if not frappe.db.exists("DocType", "Appointment Letter Template"):
        return
    comp = "middle east holidays" if frappe.db.exists("Company", "middle east holidays") else (frappe.db.get_single_value("Global Defaults", "default_company") or "")

    # Common clauses dictionary
    clauses = {
        "clause_1_appointment_scope": """1.1 You are appointed as {designation} w.e.f. {date_of_joining}, and shall report to your Reporting Manager.
1.2 Your employment shall be governed by the provisions of this Appointment Letter, the Company's HR Policies, Code of Conduct, service rules, administrative instructions, and all applicable laws and statutory regulations, as amended from time to time. You are required to comply with all such policies, rules, and procedures throughout your employment.
1.3 Your initial place of posting shall be the Company's office at {posting_location}. However, depending on business requirements, the Company reserves the right to transfer or assign you to any of its offices, branches, or any other place of business.
1.4 You shall diligently perform the duties and responsibilities assigned to you and faithfully discharge all functions relating to your position. The Company reserves the right to modify, expand, or reassign your duties, responsibilities, designation, or reporting structure from time to time based on operational, organizational, or business requirements.""",
        "clause_2_classification": """As per Company policy, you shall initially be classified as a Probationary Employee. Upon confirmation, your status shall be converted to Permanent Employee, subject to meeting performance and conduct standards.""",
        "clause_3_probation": """3.1 You will be on probation for {probation_period}, effective from your date of joining.
3.2 During the probation period, your performance, attendance, punctuality, discipline, conduct, and overall suitability for the role will be continuously monitored and evaluated. Periodic performance reviews may be conducted by your Reporting Manager in coordination with the Human Resources Department. The Company may provide feedback, guidance, and support to assist you in meeting the required performance standards.
3.3 Based on your overall performance and the Company's assessment, the Company reserves the right, at its sole discretion, to:
• Extend your probation period by up to one (1) to three (3) months, where additional time is considered necessary to evaluate your suitability; or
• Reduce or waive the remaining probation period and confirm your employment earlier in recognition of exceptional performance.
3.4 In case of performance gaps, a Performance Improvement Plan (PIP) may be issued, clearly defining expectations and timelines.
3.5 Confirmation of your employment shall be subject to your satisfactory performance, attendance, punctuality, discipline, conduct, and compliance with the Company's policies and procedures. Your employment shall be deemed confirmed only upon the issuance of a written Confirmation Letter by the Company.
3.6 The Company reserves the right to terminate employment during probation if performance, conduct, or suitability is found unsatisfactory.""",
        "clause_4_working_hours": """4.1 {company} follows a six-day work week ({working_days}).
4.2 Standard working hours shall be {working_hours}.
4.3 You shall be entitled to a {lunch_break}.""",
        "clause_5_leave_policy": """5.1 The Company's leave cycle shall be from 1st January to 31st December of each calendar year. Leave shall be governed by the Company's Leave Policy, as amended from time to time.
5.2 Employees serving under probation shall be entitled to one (1) day of paid leave for per month.
5.3 Upon successful confirmation of employment, you shall be eligible for the following annual leave entitlements:
• Casual Leave (CL): Twelve (12) days per calendar year. i.e., one (1) CL per month.
• Sick Leave (SL): Twelve (12) days per calendar year. i.e., one (1) SL per month.
5.4 Other Leave Entitlements - Employees shall also be entitled to such other leave benefits. You are advised to refer to the Company's HR Policy for detailed provisions.""",
        "clause_6_compensation": """6.1 You shall be paid a monthly gross salary of ₹{monthly_salary}/- ({monthly_salary_in_words}), the detailed salary structure of which is set out in Annexure I.
6.2 Salary shall be subject to:
• Applicable statutory deductions.
• Company policies.""",
        "clause_7_duties_conduct": """7.1 You shall faithfully, honestly, and diligently perform the duties and responsibilities assigned to you by the Company and shall devote your full working time, attention, and abilities to the business and interests of the Company.
7.2 You shall carry out all lawful instructions, directions, and assignments issued by the Company, your Reporting Manager, or any other authorized representative and shall perform your duties with due skill, care, efficiency, and professionalism.
7.3 You shall comply with the Company's policies, rules, regulations, Code of Conduct, administrative instructions, and all applicable statutory and regulatory requirements, as amended from time to time.
7.4 You shall maintain the highest standards of integrity, honesty, discipline, punctuality, confidentiality, and professional conduct at all times and shall uphold the reputation, values, and business interests of the Company.
7.5 You shall achieve the performance standards, objectives, Key Result Areas (KRAs), Key Performance Indicators (KPIs), and other targets assigned to you from time to time, subject to business requirements.
7.6 You shall protect and properly use all Company assets, property, documents, records, equipment, systems, confidential information, intellectual property, customer information, and any other resources entrusted to you, and shall not misuse or permit unauthorized use of the same.
7.7 You shall not disclose, publish, copy, remove, or misuse any confidential or proprietary information belonging to the Company during or after your employment, except as required in the ordinary course of your duties or with prior written authorization.
7.8 You shall not engage in any other employment, business, profession, consultancy, or occupation, whether paid or unpaid, without obtaining the prior written approval of the Company. You shall also avoid any activity that may give rise to a conflict of interest with the Company's business.
7.9 You shall maintain respectful and professional relationships with colleagues, customers, clients, vendors, business associates, and all other stakeholders, and shall contribute to a safe, healthy, inclusive, and harassment-free workplace.
7.10 You shall promptly report any misconduct, fraud, conflict of interest, safety hazard, security breach, policy violation, or any matter that may adversely affect the Company's operations, reputation, or legal compliance.
7.11 The Company reserves the right to modify your duties, responsibilities, reporting structure, department, or place of work from time to time based on operational, organizational, or business requirements. You shall reasonably cooperate with such changes.
7.12 Any breach of the provisions contained in this Appointment Letter, the Company's policies, or Code of Conduct, may result in disciplinary action, including suspension, recovery of losses, termination of employment, or any other action deemed appropriate by the Company in accordance with applicable law.""",
        "clause_8_dress_code": """You are required to adhere to professional dress code standards at all times.""",
        "clause_9_confidentiality": """You shall maintain strict confidentiality of all Company data, documents, and information at all times, and shall be responsible for safeguarding Company property against any misuse, loss, or damage; upon cessation of employment, you shall promptly return all Company property in your possession.""",
        "clause_10_transfer": """The Company reserves the right to transfer or assign you to any department, role, or location based on business needs.""",
        "clause_11_resignation_termination": """11.1 Either party may terminate this employment by giving thirty (30) days' prior written notice or salary in lieu of the notice period, unless otherwise specified in this Appointment Letter. The Company may, at its sole discretion, accept a shorter notice period, waive the notice period in whole or in part, or require payment of salary in lieu of the unserved portion of the notice period.
11.2 Any resignation submitted by you shall be made in writing to your Reporting Manager, with a copy to the Human Resources Department. Your resignation shall become effective only upon its acceptance by the Company, and the Company reserves the right to determine your last working day based on business and operational requirements.
11.3 During the notice period, you shall continue to diligently perform your duties and comply with all Company policies, rules, and lawful instructions. You shall not neglect your responsibilities or engage in any act prejudicial to the interests of the Company.
11.4 Before your separation from employment, you shall complete a satisfactory handover of all duties, records, documents, data, passwords, files, ongoing assignments, and any other information or responsibilities entrusted to you, as directed by your Reporting Manager or the Company.
11.5 You shall return all Company property in your possession, including but not limited to identity cards, laptops, computers, mobile devices, sim card, access cards, keys, documents, equipment, records, confidential information, and any other assets belonging to the Company before your last working day.
11.6 Leave during the notice period shall be granted only in exceptional circumstances and with prior approval. Leave taken during the Notice Period shall be considered as LOP. Any leave approved during the notice period may be treated in accordance with the Company's Leave Policy, and where applicable, may result in an extension of the notice period or deduction of salary, as determined by the Company.
11.7 Your Full and Final Settlement shall be processed only after successful completion of the notice period, return of all Company property, completion of all exit formalities, and subject to adjustment of any amounts recoverable by the Company.
11.8 The Company may conduct an exit interview as part of the separation process. Participation in such process and completion of all exit formalities shall be considered part of your obligations upon separation.
11.9 Any request for withdrawal of resignation shall be subject solely to the discretion of the Company and shall not be effective unless expressly approved in writing by the Management.
11.10 The Company reserves the right to relieve you from your duties before completion of the notice period, waive the notice period in full or in part, or make payment of salary in lieu of notice, wherever applicable, in accordance with the terms of this Appointment Letter and applicable laws.
11.11 The Company reserves the right to terminate your employment in the event of misconduct, unsatisfactory performance, violation of Company policies, or unauthorized absence, in accordance with applicable laws and Company procedures.""",
        "clause_12_general_terms": """12.1 Your appointment is subject to the satisfactory verification of your educational qualifications, experience, identity, background, and other documents submitted by you. You shall submit all documents and information required by the Company within the prescribed time. Any false declaration, suppression of material facts, forged documents, or misrepresentation shall render your employment liable to disciplinary action.
12.2 You shall promptly inform the Company in writing of any change in your personal information, including but not limited to your residential address, contact number, email address, marital status, nominee details, emergency contact details, or bank account particulars, within seven (7) days of such change.
12.3 You shall be provided with the Company's HR Policy, Code of Conduct, and other applicable policies. You are required to read, understand, and comply with the provisions contained therein and sign the prescribed acknowledgment confirming that you have read, understood, and agreed to abide by the same. Failure to comply with the Company's policies and Code of Conduct may result in disciplinary action, including termination of employment, in accordance with the applicable policies and laws.
12.4 The Company reserves the right to introduce, modify, amend, suspend, withdraw, or replace any of its policies, rules, procedures, benefits, or administrative practices at any time, in accordance with business requirements and applicable laws. Such amendments shall be binding upon you from the date they become effective.
12.5 You shall promptly comply with all lawful instructions, circulars, notifications, and administrative orders issued by the Company from time to time.
12.6 This Appointment Letter, together with the Company's policies and any annexures referred to herein, constitutes the entire understanding between you and {company} with respect to your employment and supersedes all prior discussions, representations, or communications relating to your appointment.""",
        "clause_13_policy_compliance": """You shall strictly adhere to all HR Policies, Code of Conduct, Company rules, Statutory requirements, and Administrative guidelines at all times. Non-compliance may result in disciplinary action, including termination of employment.""",
        "clause_14_acceptance": """Please sign and return a copy of this letter to confirm your acceptance of the terms and conditions of employment.""",
        "acceptance_statement": """I hereby accept the terms and conditions stated in this Appointment Letter."""
    }

    # 1. Middle East Travels Appointment Letter Template
    travels_tmpl_name = "Middle East Travels Appointment Letter Template"
    if not frappe.db.exists("Appointment Letter Template", travels_tmpl_name):
        doc_t = frappe.new_doc("Appointment Letter Template")
        doc_t.template_name = travels_tmpl_name
        doc_t.is_default = 1
        doc_t.company = comp
        doc_t.company_name_display = "Middle East Travels & Tourism"
        doc_t.reference_prefix = "METT/HR/AL"
        doc_t.letter_heading = "APPOINTMENT LETTER"
        doc_t.salutation_template = "Dear {salutation_title} {first_name},"
        doc_t.introduction = "We are pleased to appoint you at {company}, as {designation} effective from {date_of_joining}. Your employment shall be governed by the terms and conditions set forth in this Appointment Letter and the Company’s policies, as amended from time to time, and you shall be bound by all such rules, regulations, and procedures as may be prescribed by the Management."
        for k, v in clauses.items():
            setattr(doc_t, k, v)
        doc_t.signatory_company_label = "For Middle East Travels & Tourism"
        doc_t.default_hr_signatory_name = "Gopika"
        doc_t.default_hr_signatory_designation = "HR Consultant"
        doc_t.default_hr_signatory_title = "Authorized Signatory"
        doc_t.footer_address = "Shobha Tower, 5/3412L, Mavoor Rd, near Emerald Mall, Arayidathupalam, Kozhikode, Kerala 673004"
        doc_t.footer_contact = "Tel: 91 8593944666, 91 7025144666"
        doc_t.footer_email_web = "info@middleeasttravels.in | www.middleeasttravels.in"
        doc_t.flags.ignore_permissions = True
        doc_t.insert()
        print("Seeded Middle East Travels Appointment Letter Template")

    # 2. Middle East Holidays Appointment Letter Template
    holidays_tmpl_name = "Middle East Holidays Appointment Letter Template"
    if not frappe.db.exists("Appointment Letter Template", holidays_tmpl_name):
        doc_h = frappe.new_doc("Appointment Letter Template")
        doc_h.template_name = holidays_tmpl_name
        doc_h.is_default = 0
        doc_h.company = comp
        doc_h.company_name_display = "Middle East Holidays"
        doc_h.reference_prefix = "MEH/HR/AL"
        doc_h.letter_heading = "APPOINTMENT LETTER"
        doc_h.salutation_template = "Dear {salutation_title} {first_name},"
        doc_h.introduction = "We are pleased to appoint you at {company}, as {designation} effective from {date_of_joining}. Your employment shall be governed by the terms and conditions set forth in this Appointment Letter and the Company’s policies, as amended from time to time, and you shall be bound by all such rules, regulations, and procedures as may be prescribed by the Management."
        for k, v in clauses.items():
            # Replace Travels with Holidays if explicitly in clause
            val = v.replace("Middle East Travels & Tourism", "Middle East Holidays").replace("Middle East Travels", "Middle East Holidays")
            setattr(doc_h, k, val)
        doc_h.signatory_company_label = "For Middle East Holidays"
        doc_h.default_hr_signatory_name = "Gopika"
        doc_h.default_hr_signatory_designation = "HR Consultant"
        doc_h.default_hr_signatory_title = "Authorized Signatory"
        doc_h.footer_address = "Shobha Tower, 5/3412L, Mavoor Rd, near Emerald Mall, Arayidathupalam, Kozhikode, Kerala 673004"
        doc_h.footer_contact = "Tel: 91 8593944666, 91 7025144666"
        doc_h.footer_email_web = "info@middleeastholidays.in | www.middleeastholidays.in"
        doc_h.flags.ignore_permissions = True
        doc_h.insert()
        print("Seeded Middle East Holidays Appointment Letter Template")
