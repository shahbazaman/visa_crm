# -*- coding: utf-8 -*-
import re
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import formatdate, money_in_words

class EmployeeOfferLetter(Document):
    def autoname(self):
        from frappe.model.naming import make_autoname
        if not self.naming_series:
            self.naming_series = "OFFER-.####"
        self.name = make_autoname(self.naming_series)

        # Extract sequential integer for offer_number e.g. '0001'
        parts = self.name.split("-")
        if len(parts) > 1 and parts[-1].isdigit():
            self.offer_number = parts[-1]
            num = int(parts[-1])
            self.reference_number = f"ME/HRD/OL/{num:02d}"
        else:
            self.offer_number = self.name
            self.reference_number = f"ME/HRD/OL/{self.name}"

    def validate(self):
        self.validate_employee_data()
        self.calculate_salary_in_words()
        self.populate_from_template()
        self.resolve_all_placeholders()

    def validate_employee_data(self):
        if self.employee:
            emp = frappe.db.get_value(
                "Employee",
                self.employee,
                ["employee_name", "first_name", "designation", "department", "date_of_joining", "custom_monthly_salary", "custom_is_on_probation", "current_address", "permanent_address"],
                as_dict=True
            )
            if emp:
                if not self.employee_name:
                    self.employee_name = emp.employee_name
                if not self.first_name:
                    self.first_name = emp.first_name or (emp.employee_name.split()[0] if emp.employee_name else "")
                if not self.designation and emp.designation:
                    self.designation = emp.designation
                if not self.department and emp.department:
                    self.department = emp.department
                if not self.date_of_joining and emp.date_of_joining:
                    self.date_of_joining = emp.date_of_joining
                if not self.monthly_salary and emp.custom_monthly_salary:
                    self.monthly_salary = emp.custom_monthly_salary
                if self.probation is None and emp.custom_is_on_probation is not None:
                    self.probation = emp.custom_is_on_probation
                if not self.address:
                    self.address = emp.current_address or emp.permanent_address or ""

    def calculate_salary_in_words(self):
        if self.monthly_salary:
            words = money_in_words(self.monthly_salary, "INR")
            # Clean up standard formatting: "INR Eighteen Thousand only." -> "Rupees Eighteen Thousand Only"
            cleaned = words.replace("INR ", "Rupees ").replace(" only.", " Only").replace(" Only.", " Only").replace(" only", " Only")
            if not cleaned.endswith("Only"):
                cleaned += " Only"
            self.monthly_salary_in_words = cleaned

    def populate_from_template(self):
        if not self.offer_letter_template:
            default_tmpl = frappe.db.get_value("Offer Letter Template", {"is_default": 1}, "name")
            if not default_tmpl:
                default_tmpl = frappe.db.get_value("Offer Letter Template", {}, "name")
            if default_tmpl:
                self.offer_letter_template = default_tmpl

        if not self.offer_letter_template:
            return

        tmpl = frappe.get_doc("Offer Letter Template", self.offer_letter_template)

        # Inherit branding assets if not already overridden
        if not self.company_logo and tmpl.get("company_logo"):
            self.company_logo = tmpl.company_logo
        if not self.iata_logo and tmpl.get("iata_logo"):
            self.iata_logo = tmpl.iata_logo
        if not self.signature_image and tmpl.get("signature_image"):
            self.signature_image = tmpl.signature_image

        subs = self._build_substitution_dict(tmpl)

        # Populate sections if empty
        first_name = self.first_name or (self.employee_name.split()[0] if self.employee_name else "Candidate")
        if not self.salutation:
            self.salutation = f"Dear Mr./Ms. {first_name},"
        if not self.introduction and tmpl.introduction:
            self.introduction = self._render_string(tmpl.introduction, subs)
        if not self.compensation_details and tmpl.compensation_text:
            self.compensation_details = self._render_string(tmpl.compensation_text, subs)
        if not self.probation_details and tmpl.probation_text:
            self.probation_details = self._render_string(tmpl.probation_text, subs)
        if not self.performance_reviews and tmpl.performance_review_text:
            self.performance_reviews = self._render_string(tmpl.performance_review_text, subs)
        if not self.working_hours_details and tmpl.working_hours_text:
            self.working_hours_details = self._render_string(tmpl.working_hours_text, subs)
        if not self.leave_details and tmpl.leave_text:
            self.leave_details = self._render_string(tmpl.leave_text, subs)
        if not self.notice_period_details and tmpl.notice_period_text:
            self.notice_period_details = self._render_string(tmpl.notice_period_text, subs)
        if not self.joining_details and tmpl.joining_details_text:
            self.joining_details = self._render_string(tmpl.joining_details_text, subs)
        if not self.required_documents and tmpl.required_documents_text:
            self.required_documents = self._render_string(tmpl.required_documents_text, subs)
        if not self.acceptance_terms and tmpl.acceptance_text:
            self.acceptance_terms = self._render_string(tmpl.acceptance_text, subs)

        if not self.hr_signatory_name:
            self.hr_signatory_name = tmpl.default_hr_signatory_name or "Gopika"
        if not self.hr_signatory_designation:
            self.hr_signatory_designation = tmpl.default_hr_signatory_designation or "HR Consultant"
        if not self.hr_signatory_title:
            self.hr_signatory_title = tmpl.default_hr_signatory_title or "Authorized Signatory"
        if not self.signatory_company_label:
            self.signatory_company_label = tmpl.signatory_company_label or "For, Middle East Travels & Tourism"

    def _build_substitution_dict(self, tmpl=None):
        desig = self.designation or "Sales & Marketing Executive"
        comp = self.company_name_display or (tmpl.company_name_display if tmpl else "Middle East Travels & Tourism")
        first_name = self.first_name or (self.employee_name.split()[0] if self.employee_name else "Candidate")
        sal_formatted = f"{self.monthly_salary:,.2f}".rstrip("0").rstrip(".") if self.monthly_salary else "18,000"
        sal_words = self.monthly_salary_in_words or "Rupees Eighteen Thousand Only"
        doj_str = formatdate(self.date_of_joining, "dd.mm.yyyy") if self.date_of_joining else "11.09.2026"
        doj_formatted = formatdate(self.date_of_joining, "d MMMM yyyy") if self.date_of_joining else "11th September 2026"
        prob_period = self.probation_period or "three (3) months"
        hrs = self.working_hours or "Monday to Saturday, 10:00 AM to 5:30 PM"
        time_str = self.joining_time or "10:30 AM"

        return {
            "designation": desig,
            "company": comp,
            "first_name": first_name,
            "employee_name": self.employee_name or "Candidate",
            "monthly_salary": sal_formatted,
            "monthly_salary_in_words": sal_words,
            "date_of_joining": doj_str,
            "joining_date_formatted": doj_formatted,
            "probation_period": prob_period,
            "working_hours": hrs,
            "joining_time": time_str
        }

    def resolve_all_placeholders(self):
        """Final cleanup pass: ensure NO {variable} remains in any clause!"""
        subs = self._build_substitution_dict()
        clauses = [
            "salutation", "introduction", "compensation_details", "probation_details",
            "performance_reviews", "working_hours_details", "leave_details",
            "notice_period_details", "joining_details", "required_documents", "acceptance_terms"
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
        self.issued_date = frappe.utils.now_datetime()
        self.db_set("status", "Issued")
        self.db_set("issued_by", self.issued_by)
        self.db_set("issued_date", self.issued_date)

    def on_cancel(self):
        self.status = "Cancelled"
        self.db_set("status", "Cancelled")
