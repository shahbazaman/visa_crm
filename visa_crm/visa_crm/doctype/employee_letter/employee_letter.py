# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.model.document import Document

class EmployeeLetter(Document):
    def autoname(self):
        if self.letter_type == "Offer Letter":
            self.naming_series = "OFFER-.YYYY.-.#####"
        elif self.letter_type == "Appointment Letter":
            self.naming_series = "APPT-.YYYY.-.#####"
        elif self.letter_type == "Increment Letter":
            self.naming_series = "INCR-.YYYY.-.#####"

    def validate(self):
        self.set_naming_series()
        self.validate_applicant_or_employee()
        self.calculate_increment()
        self.generate_default_content()

    def set_naming_series(self):
        if self.letter_type == "Offer Letter" and not self.naming_series.startswith("OFFER-"):
            self.naming_series = "OFFER-.YYYY.-.#####"
        elif self.letter_type == "Appointment Letter" and not self.naming_series.startswith("APPT-"):
            self.naming_series = "APPT-.YYYY.-.#####"
        elif self.letter_type == "Increment Letter" and not self.naming_series.startswith("INCR-"):
            self.naming_series = "INCR-.YYYY.-.#####"

    def validate_applicant_or_employee(self):
        if self.letter_type in ["Appointment Letter", "Increment Letter"] and not self.employee:
            frappe.throw(_("Employee is mandatory for {0}").format(self.letter_type))
        if self.employee and not self.applicant_name:
            self.applicant_name = frappe.db.get_value("Employee", self.employee, "employee_name")

    def calculate_increment(self):
        if self.letter_type == "Increment Letter" and self.previous_salary and self.new_salary:
            self.increment_amount = float(self.new_salary) - float(self.previous_salary)
            if float(self.previous_salary) > 0:
                self.increment_percentage = round((self.increment_amount / float(self.previous_salary)) * 100, 2)
            if not self.monthly_salary:
                self.monthly_salary = self.new_salary

        if self.monthly_salary and not self.annual_ctc:
            self.annual_ctc = float(self.monthly_salary) * 12

    def generate_default_content(self):
        if not self.content:
            company_name = frappe.db.get_value("Company", self.company, "company_name") or self.company
            signatory = frappe.db.get_value("Employee", self.authorized_signatory, "employee_name") or "Authorized Signatory"
            name = self.applicant_name or "Candidate"
            desig = self.designation or "Team Member"

            if self.letter_type == "Offer Letter":
                self.content = f"""<p>Dear <strong>{name}</strong>,</p>
<p>We are pleased to offer you the position of <strong>{desig}</strong> with <strong>{company_name}</strong>.</p>
<p>Your scheduled joining date is <strong>{self.date_of_joining or 'TBD'}</strong> at our <strong>{self.work_location or 'Main'}</strong> office.</p>
<p>Your Monthly Gross Salary will be <strong>INR {self.monthly_salary or 0:,.2f}</strong> (Annual CTC: INR {self.annual_ctc or 0:,.2f}).</p>
<p>Please review and sign this offer letter as acceptance of our offer.</p>
<br>
<p>Sincerely,</p>
<p><strong>{signatory}</strong><br>{self.signatory_designation or 'Human Resources'}<br>{company_name}</p>"""
            elif self.letter_type == "Appointment Letter":
                self.content = f"""<p>Dear <strong>{name}</strong>,</p>
<p>This has reference to your application and subsequent interviews with us. We are delighted to appoint you as <strong>{desig}</strong> at <strong>{company_name}</strong> effective <strong>{self.date_of_joining or self.letter_date}</strong>.</p>
<p>You will be on probation for a period of <strong>{self.probation_period or '3 Months'}</strong>.</p>
<p>Your compensation details are as follows:</p>
<ul>
  <li>Monthly Gross Salary: <strong>INR {self.monthly_salary or 0:,.2f}</strong></li>
  <li>Annual Cost to Company (CTC): <strong>INR {self.annual_ctc or 0:,.2f}</strong></li>
</ul>
<p>We welcome you to our team and look forward to a long and fruitful association.</p>
<br>
<p>Warm regards,</p>
<p><strong>{signatory}</strong><br>{self.signatory_designation or 'Human Resources'}<br>{company_name}</p>"""
            elif self.letter_type == "Increment Letter":
                self.content = f"""<p>Dear <strong>{name}</strong>,</p>
<p>In recognition of your performance and contributions to <strong>{company_name}</strong>, we are pleased to inform you that your compensation has been revised effective <strong>{self.effective_date or self.letter_date}</strong>.</p>
<p><strong>Salary Revision Details:</strong></p>
<ul>
  <li>Previous Monthly Gross: INR {self.previous_salary or 0:,.2f}</li>
  <li>Revised Monthly Gross: <strong>INR {self.new_salary or 0:,.2f}</strong></li>
  <li>Increment Amount: INR {self.increment_amount or 0:,.2f} ({self.increment_percentage or 0}%)</li>
  <li>Revised Annual CTC: INR {self.annual_ctc or 0:,.2f}</li>
</ul>
<p>We look forward to your continued dedication and excellence.</p>
<br>
<p>Best regards,</p>
<p><strong>{signatory}</strong><br>{self.signatory_designation or 'Management'}<br>{company_name}</p>"""

    def on_submit(self):
        self.status = "Issued"
        self.issued_by = frappe.session.user
        self.issued_date = frappe.utils.now_datetime()
        self.db_set("status", "Issued")
        self.db_set("issued_by", self.issued_by)
        self.db_set("issued_date", self.issued_date)

    def on_cancel(self):
        self.status = "Archived"
        self.db_set("status", "Archived")
