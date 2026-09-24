# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import formatdate, money_in_words, now_datetime

class EmployeeAppointmentLetter(Document):
    def autoname(self):
        from frappe.model.naming import make_autoname
        if not self.naming_series:
            self.naming_series = "APPT-.####"
        self.name = make_autoname(self.naming_series)

        parts = self.name.split("-")
        if len(parts) > 1 and parts[-1].isdigit():
            self.appointment_number = parts[-1]
            num = int(parts[-1])
        else:
            self.appointment_number = self.name
            num = 1

        is_holidays = "holiday" in (self.company_name_display or "").lower() or "holiday" in (self.company or "").lower()
        prefix = "MEH/HR/AL" if is_holidays else "METT/HR/AL"
        year = formatdate(self.letter_date, "yyyy") if self.letter_date else "2026"
        self.reference_number = f"{prefix}/{num:02d}/{year}"

    def validate(self):
        self.validate_employee_data()
        self.calculate_salary_and_annexure()
        self.populate_from_template()
        self.resolve_all_placeholders()

    def validate_employee_data(self):
        if self.employee:
            emp = frappe.db.get_value(
                "Employee",
                self.employee,
                ["employee_name", "first_name", "salutation", "designation", "department", "date_of_joining", "custom_monthly_salary", "current_address", "permanent_address"],
                as_dict=True
            )
            if emp:
                if not self.employee_name:
                    self.employee_name = emp.employee_name
                if not self.first_name:
                    self.first_name = emp.first_name or (emp.employee_name.split()[0] if emp.employee_name else "")
                if not self.salutation_title and emp.salutation:
                    self.salutation_title = emp.salutation
                if not self.designation and emp.designation:
                    self.designation = emp.designation
                if not self.department and emp.department:
                    self.department = emp.department
                if not self.date_of_joining and emp.date_of_joining:
                    self.date_of_joining = emp.date_of_joining
                if not self.monthly_salary and emp.custom_monthly_salary:
                    self.monthly_salary = emp.custom_monthly_salary
                if not self.address:
                    self.address = emp.current_address or emp.permanent_address or ""

    def calculate_salary_and_annexure(self):
        if self.monthly_salary:
            sal = float(self.monthly_salary)
            words = money_in_words(sal, "INR")
            cleaned = words.replace("INR ", "Rupees ").replace(" only.", " Only").replace(" Only.", " Only").replace(" only", " Only")
            if not cleaned.endswith("Only"):
                cleaned += " Only"
            self.monthly_salary_in_words = cleaned
            self.annual_ctc = sal * 12

            # Compute Annexure I breakdown if not manually specified
            if not self.basic_salary_monthly:
                self.basic_salary_monthly = round(sal * 0.50)
                self.basic_salary_annual = self.basic_salary_monthly * 12
            elif not self.basic_salary_annual:
                self.basic_salary_annual = float(self.basic_salary_monthly) * 12

            if not self.da_monthly:
                self.da_monthly = round(sal * 0.10)
                self.da_annual = self.da_monthly * 12
            elif not self.da_annual:
                self.da_annual = float(self.da_monthly) * 12

            if not self.hra_monthly:
                self.hra_monthly = round(sal * 0.20)
                self.hra_annual = self.hra_monthly * 12
            elif not self.hra_annual:
                self.hra_annual = float(self.hra_monthly) * 12

            if not self.other_allowances_monthly:
                self.other_allowances_monthly = round(sal * 0.20)
                self.other_allowances_annual = self.other_allowances_monthly * 12
            elif not self.other_allowances_annual:
                self.other_allowances_annual = float(self.other_allowances_monthly) * 12

            if not self.gross_salary_monthly:
                self.gross_salary_monthly = sal
                self.gross_salary_annual = self.annual_ctc

            if not self.employer_pf_monthly:
                self.employer_pf_monthly = "NA"
                self.employer_pf_annual = "NA"

            if not self.employer_esi_monthly:
                self.employer_esi_monthly = "NA"
                self.employer_esi_annual = "NA"

            if not self.ctc_monthly:
                self.ctc_monthly = sal
                self.ctc_annual = self.annual_ctc

    def populate_from_template(self):
        if not self.appointment_letter_template:
            is_holidays = "holiday" in (self.company_name_display or "").lower() or "holiday" in (self.company or "").lower()
            target_filter = {"template_name": ["like", "%Holiday%"]} if is_holidays else {"template_name": ["like", "%Travel%"]}
            default_tmpl = frappe.db.get_value("Appointment Letter Template", target_filter, "name")
            if not default_tmpl:
                default_tmpl = frappe.db.get_value("Appointment Letter Template", {"is_default": 1}, "name")
            if not default_tmpl:
                default_tmpl = frappe.db.get_value("Appointment Letter Template", {}, "name")
            if default_tmpl:
                self.appointment_letter_template = default_tmpl

        if not self.appointment_letter_template:
            return

        tmpl = frappe.get_doc("Appointment Letter Template", self.appointment_letter_template)

        # Inherit branding if empty
        if not self.company_logo and tmpl.get("company_logo"):
            self.company_logo = tmpl.company_logo
        if not self.iata_logo and tmpl.get("iata_logo"):
            self.iata_logo = tmpl.iata_logo
        if not self.signature_image and tmpl.get("signature_image"):
            self.signature_image = tmpl.signature_image

        subs = self._build_substitution_dict(tmpl)

        # Populate salutation line
        title = self.salutation_title or "Ms."
        fname = self.first_name or (self.employee_name.split()[0] if self.employee_name else "Candidate")
        if not self.salutation:
            self.salutation = f"Dear {title} {fname},"

        # Populate clauses if empty
        clauses_mapping = [
            ("introduction", "introduction"),
            ("clause_1_appointment_scope", "clause_1_appointment_scope"),
            ("clause_2_classification", "clause_2_classification"),
            ("clause_3_probation", "clause_3_probation"),
            ("clause_4_working_hours", "clause_4_working_hours"),
            ("clause_5_leave_policy", "clause_5_leave_policy"),
            ("clause_6_compensation", "clause_6_compensation"),
            ("clause_7_duties_conduct", "clause_7_duties_conduct"),
            ("clause_8_dress_code", "clause_8_dress_code"),
            ("clause_9_confidentiality", "clause_9_confidentiality"),
            ("clause_10_transfer", "clause_10_transfer"),
            ("clause_11_resignation_termination", "clause_11_resignation_termination"),
            ("clause_12_general_terms", "clause_12_general_terms"),
            ("clause_13_policy_compliance", "clause_13_policy_compliance"),
            ("clause_14_acceptance", "clause_14_acceptance"),
            ("acceptance_statement", "acceptance_statement"),
        ]

        for target_field, tmpl_field in clauses_mapping:
            if not getattr(self, target_field, None) and tmpl.get(tmpl_field):
                setattr(self, target_field, self._render_string(tmpl.get(tmpl_field), subs))

        # Signatory defaults
        if not self.hr_signatory_name:
            self.hr_signatory_name = tmpl.default_hr_signatory_name or "Gopika"
        if not self.hr_signatory_designation:
            self.hr_signatory_designation = tmpl.default_hr_signatory_designation or "HR Consultant"
        if not self.hr_signatory_title:
            self.hr_signatory_title = tmpl.default_hr_signatory_title or "Authorized Signatory"
        if not self.signatory_company_label:
            comp_display = self.company_name_display or tmpl.company_name_display or "Middle East Travels & Tourism"
            self.signatory_company_label = tmpl.signatory_company_label or f"For {comp_display}"

    def _build_substitution_dict(self, tmpl=None):
        desig = self.designation or "Accounts Assistant"
        comp = self.company_name_display or (tmpl.company_name_display if tmpl else "Middle East Travels & Tourism")
        title = self.salutation_title or "Ms."
        fname = self.first_name or (self.employee_name.split()[0] if self.employee_name else "Candidate")
        sal_formatted = f"{self.monthly_salary:,.0f}" if self.monthly_salary else "15,000"
        sal_words = self.monthly_salary_in_words or "Rupees Fifteen Thousand Only"
        doj_str = formatdate(self.date_of_joining, "dd.mm.yyyy") if self.date_of_joining else "17.08.2026"
        prob_period = self.probation_period or "three (3) months"
        hrs = self.working_hours or "10:00 AM to 5:30 PM"
        days = self.working_days or "Monday to Saturday"
        lunch = self.lunch_break or "forty (40) minute lunch break between 1:00 PM and 2:30 PM"
        posting = self.posting_location or "Calicut"

        return {
            "designation": desig,
            "company": comp,
            "company_name": comp,
            "salutation_title": title,
            "first_name": fname,
            "employee_name": self.employee_name or "Candidate",
            "monthly_salary": sal_formatted,
            "monthly_salary_in_words": sal_words,
            "date_of_joining": doj_str,
            "probation_period": prob_period,
            "working_hours": hrs,
            "working_days": days,
            "lunch_break": lunch,
            "posting_location": posting
        }

    def resolve_all_placeholders(self):
        subs = self._build_substitution_dict()
        clauses = [
            "salutation", "introduction", "clause_1_appointment_scope",
            "clause_2_classification", "clause_3_probation", "clause_4_working_hours",
            "clause_5_leave_policy", "clause_6_compensation", "clause_7_duties_conduct",
            "clause_8_dress_code", "clause_9_confidentiality", "clause_10_transfer",
            "clause_11_resignation_termination", "clause_12_general_terms",
            "clause_13_policy_compliance", "clause_14_acceptance", "acceptance_statement"
        ]
        for field in clauses:
            val = getattr(self, field, None)
            if val and isinstance(val, str) and "{" in val and "}" in val:
                setattr(self, field, self._render_string(val, subs))

    def _render_string(self, text, context):
        if not text:
            return ""
        rendered = text
        for k, v in context.items():
            rendered = rendered.replace(f"{{{k}}}", str(v))
        return rendered

    def on_submit(self):
        self.status = "Issued"
        self.issued_by = frappe.session.user
        self.issued_date = now_datetime()
        self.db_set("status", "Issued")
        self.db_set("issued_by", self.issued_by)
        self.db_set("issued_date", self.issued_date)

    def on_cancel(self):
        self.status = "Cancelled"
        self.db_set("status", "Cancelled")
