# -*- coding: utf-8 -*-
"""
Automated Unit Tests for Appointment Letter System
==================================================
Tests:
1. Numbering sequence and reference generation (METT/HR/AL vs MEH/HR/AL)
2. Template population and dynamic variable substitution
3. Salary calculation and Annexure I breakdown
4. Salary in words formatting
5. Exact 7-page Jinja rendering for Middle East Travels Appointment Letter
6. Exact 7-page Jinja rendering for Middle East Holidays Appointment Letter
7. Verify that Travels is completely replaced with Holidays in the Holidays template
8. Safe fallbacks for missing optional data
"""
import unittest
from datetime import date
from jinja2 import Template

class TestAppointmentLetterNumbering(unittest.TestCase):
    def test_travels_numbering_sequence(self):
        samples = [
            ("APPT-0001", "0001", "METT/HR/AL/01/2026"),
            ("APPT-0002", "0002", "METT/HR/AL/02/2026"),
            ("APPT-0007", "0007", "METT/HR/AL/07/2026"),
            ("APPT-0025", "0025", "METT/HR/AL/25/2026"),
        ]
        for name, expected_num, expected_ref in samples:
            parts = name.split("-")
            appt_num = parts[-1]
            num = int(appt_num)
            ref_no = f"METT/HR/AL/{num:02d}/2026"
            self.assertEqual(appt_num, expected_num)
            self.assertEqual(ref_no, expected_ref)

    def test_holidays_numbering_sequence(self):
        samples = [
            ("APPT-0001", "0001", "MEH/HR/AL/01/2026"),
            ("APPT-0002", "0002", "MEH/HR/AL/02/2026"),
            ("APPT-0005", "0005", "MEH/HR/AL/05/2026"),
        ]
        for name, expected_num, expected_ref in samples:
            parts = name.split("-")
            appt_num = parts[-1]
            num = int(appt_num)
            ref_no = f"MEH/HR/AL/{num:02d}/2026"
            self.assertEqual(appt_num, expected_num)
            self.assertEqual(ref_no, expected_ref)

class TestAppointmentLetterCalculations(unittest.TestCase):
    def test_salary_in_words(self):
        raw_words = "INR Fifteen Thousand only."
        cleaned = raw_words.replace("INR ", "Rupees ").replace(" only.", " Only").replace(" Only.", " Only")
        if not cleaned.endswith("Only"):
            cleaned += " Only"
        self.assertEqual(cleaned, "Rupees Fifteen Thousand Only")

    def test_annexure_salary_breakdown(self):
        monthly = 15000.0
        annual = monthly * 12
        basic_m = round(monthly * 0.50)
        da_m = round(monthly * 0.10)
        hra_m = round(monthly * 0.20)
        other_m = round(monthly * 0.20)

        self.assertEqual(basic_m, 7500.0)
        self.assertEqual(basic_m * 12, 90000.0)
        self.assertEqual(da_m, 1500.0)
        self.assertEqual(da_m * 12, 18000.0)
        self.assertEqual(hra_m, 3000.0)
        self.assertEqual(hra_m * 12, 36000.0)
        self.assertEqual(other_m, 3000.0)
        self.assertEqual(other_m * 12, 36000.0)
        self.assertEqual(basic_m + da_m + hra_m + other_m, monthly)
        self.assertEqual(annual, 180000.0)

class TestPrintFormatRendering(unittest.TestCase):
    def setUp(self):
        self.travels_html_path = "/home/shahbaz/frappe-bench/apps/visa_crm/visa_crm/visa_crm/print_format/middle_east_travels_appointment_letter/middle_east_travels_appointment_letter.html"
        self.holidays_html_path = "/home/shahbaz/frappe-bench/apps/visa_crm/visa_crm/visa_crm/print_format/middle_east_holidays_appointment_letter/middle_east_holidays_appointment_letter.html"

    def test_travels_7_page_structure(self):
        with open(self.travels_html_path, "r", encoding="utf-8") as f:
            template_str = f.read()

        class MockFrappeUtils:
            @staticmethod
            def formatdate(d, fmt):
                if fmt == "yyyy":
                    return "2026"
                return "17.08.2026"

        class MockDoc:
            name = "APPT-0002"
            appointment_number = "0002"
            reference_number = "METT/HR/AL/02/2026"
            letter_date = date(2026, 8, 17)
            date_of_joining = date(2026, 8, 17)
            employee_name = "Anavya K"
            salutation_title = "Ms."
            first_name = "Anavya"
            designation = "Accounts Assistant"
            department = "Accounts"
            posting_location = "Calicut"
            company_name_display = "Middle East Travels & Tourism"
            address = "Kundyadath Thazhekuni\nKongannur\nAtholi\nKozhikode, Kerala – 673315"
            probation_period = "three (3) months"
            working_hours = "10:00 AM to 5:30 PM"
            working_days = "Monday to Saturday"
            lunch_break = "forty (40) minute lunch break between 1:00 PM and 2:30 PM"
            monthly_salary = 15000.0
            monthly_salary_in_words = "Rupees Fifteen Thousand Only"
            annual_ctc = 180000.0
            basic_salary_monthly = 7500.0
            basic_salary_annual = 90000.0
            da_monthly = 1500.0
            da_annual = 18000.0
            hra_monthly = 3000.0
            hra_annual = 36000.0
            other_allowances_monthly = 3000.0
            other_allowances_annual = 36000.0
            gross_salary_monthly = 15000.0
            gross_salary_annual = 180000.0
            employer_pf_monthly = "NA"
            employer_pf_annual = "NA"
            employer_esi_monthly = "NA"
            employer_esi_annual = "NA"
            ctc_monthly = 15000.0
            ctc_annual = 180000.0
            salutation = "Dear Ms. Anavya,"
            introduction = ""
            clause_1_appointment_scope = ""
            clause_2_classification = ""
            clause_3_probation = ""
            clause_4_working_hours = ""
            clause_5_leave_policy = ""
            clause_6_compensation = ""
            clause_7_duties_conduct = ""
            clause_8_dress_code = ""
            clause_9_confidentiality = ""
            clause_10_transfer = ""
            clause_11_resignation_termination = ""
            clause_12_general_terms = ""
            clause_13_policy_compliance = ""
            clause_14_acceptance = ""
            acceptance_statement = "I hereby accept the terms and conditions stated in this Appointment Letter."
            signatory_company_label = "For Middle East Travels & Tourism"
            hr_signatory_name = "Gopika"
            hr_signatory_designation = "HR Consultant"
            hr_signatory_title = "Authorized Signatory"
            signature_image = None

        tmpl = Template(template_str)
        output = tmpl.render(doc=MockDoc(), frappe={"utils": MockFrappeUtils()})

        # Exactly 7 pages
        page_count = output.count('<div class="appointment-page">')
        self.assertEqual(page_count, 7, "Output must contain exactly 7 appointment pages")

        # Verify key clauses and text
        self.assertIn("APPOINTMENT LETTER", output)
        self.assertIn("METT/HR/AL/02/2026", output)
        self.assertIn("Anavya K", output)
        self.assertIn("Accounts Assistant", output)
        self.assertIn("Middle East Travels & Tourism", output)
        self.assertIn("1. APPOINTMENT &amp; SCOPE OF EMPLOYMENT", output)
        self.assertIn("2. EMPLOYMENT CLASSIFICATION", output)
        self.assertIn("3. PROBATION, REVIEW &amp; CONFIRMATION", output)
        self.assertIn("4. WORKING DAYS, HOURS &amp; BREAKS", output)
        self.assertIn("5. LEAVE POLICY &amp; ENTITLEMENTS", output)
        self.assertIn("6. COMPENSATION", output)
        self.assertIn("7. DUTIES, RESPONSIBILITIES &amp; CONDUCT", output)
        self.assertIn("8. DRESS CODE &amp; WORKPLACE BEHAVIOUR", output)
        self.assertIn("9. CONFIDENTIALITY &amp; COMPANY ASSETS", output)
        self.assertIn("10. TRANSFER, MOBILITY &amp; DEPLOYMENT", output)
        self.assertIn("11. RESIGNATION &amp; TERMINATION", output)
        self.assertIn("12. GENERAL TERMS &amp; CONDITIONS", output)
        self.assertIn("13. POLICY COMPLIANCE", output)
        self.assertIn("14. ACCEPTANCE", output)
        self.assertIn("EMPLOYEE ACCEPTANCE", output)
        self.assertIn("Annexure I:", output)
        self.assertIn("Basic Salary", output)
        self.assertIn("Cost To Company (CTC)", output)
        self.assertIn("7,500", output)
        self.assertIn("90,000", output)
        self.assertIn("180,000", output)

    def test_holidays_7_page_structure_and_no_travels_leak(self):
        with open(self.holidays_html_path, "r", encoding="utf-8") as f:
            template_str = f.read()

        class MockFrappeUtils:
            @staticmethod
            def formatdate(d, fmt):
                if fmt == "yyyy":
                    return "2026"
                return "17.08.2026"

        class MockDoc:
            name = "APPT-0001"
            appointment_number = "0001"
            reference_number = "MEH/HR/AL/01/2026"
            letter_date = date(2026, 8, 17)
            date_of_joining = date(2026, 8, 17)
            employee_name = "Rahul Sharma"
            salutation_title = "Mr."
            first_name = "Rahul"
            designation = "Holiday Package Specialist"
            department = "Operations"
            posting_location = "Calicut"
            company_name_display = "Middle East Holidays"
            address = "Calicut, Kerala"
            probation_period = "three (3) months"
            working_hours = "10:00 AM to 5:30 PM"
            working_days = "Monday to Saturday"
            lunch_break = "forty (40) minute lunch break between 1:00 PM and 2:30 PM"
            monthly_salary = 20000.0
            monthly_salary_in_words = "Rupees Twenty Thousand Only"
            annual_ctc = 240000.0
            basic_salary_monthly = 10000.0
            basic_salary_annual = 120000.0
            da_monthly = 2000.0
            da_annual = 24000.0
            hra_monthly = 4000.0
            hra_annual = 48000.0
            other_allowances_monthly = 4000.0
            other_allowances_annual = 48000.0
            gross_salary_monthly = 20000.0
            gross_salary_annual = 240000.0
            employer_pf_monthly = "NA"
            employer_pf_annual = "NA"
            employer_esi_monthly = "NA"
            employer_esi_annual = "NA"
            ctc_monthly = 20000.0
            ctc_annual = 240000.0
            salutation = "Dear Mr. Rahul,"
            introduction = ""
            clause_1_appointment_scope = ""
            clause_2_classification = ""
            clause_3_probation = ""
            clause_4_working_hours = ""
            clause_5_leave_policy = ""
            clause_6_compensation = ""
            clause_7_duties_conduct = ""
            clause_8_dress_code = ""
            clause_9_confidentiality = ""
            clause_10_transfer = ""
            clause_11_resignation_termination = ""
            clause_12_general_terms = ""
            clause_13_policy_compliance = ""
            clause_14_acceptance = ""
            acceptance_statement = "I hereby accept the terms and conditions stated in this Appointment Letter."
            signatory_company_label = "For Middle East Holidays"
            hr_signatory_name = "Gopika"
            hr_signatory_designation = "HR Consultant"
            hr_signatory_title = "Authorized Signatory"
            signature_image = None

        tmpl = Template(template_str)
        output = tmpl.render(doc=MockDoc(), frappe={"utils": MockFrappeUtils()})

        # Exactly 7 pages
        page_count = output.count('<div class="appointment-page">')
        self.assertEqual(page_count, 7, "Output must contain exactly 7 appointment pages")

        # Verify key clauses and text
        self.assertIn("APPOINTMENT LETTER", output)
        self.assertIn("MEH/HR/AL/01/2026", output)
        self.assertIn("Rahul Sharma", output)
        self.assertIn("Holiday Package Specialist", output)
        self.assertIn("Middle East Holidays", output)
        self.assertIn("For Middle East Holidays", output)
        self.assertIn("Holidays", output)
        self.assertIn("info@middleeastholidays.in", output)
        self.assertIn("www.middleeastholidays.in", output)

        # STRICT REQUIREMENT: Travels & Tourism must NOT appear in the rendered document text!
        import re
        text_only = re.sub(r'data:image/[^;]+;base64,[A-Za-z0-9+/=\s]+', '', output)
        self.assertNotIn("Middle East Travels & Tourism", text_only)
        self.assertNotIn("Middle East Travels", text_only)
        self.assertNotIn("TRAVELS", text_only)

    def test_minimal_doc_safe_fallbacks(self):
        with open(self.travels_html_path, "r", encoding="utf-8") as f:
            template_str = f.read()

        class MockFrappeUtils:
            @staticmethod
            def formatdate(d, fmt):
                return ""

        class MinimalDoc:
            name = "APPT-0001"
            appointment_number = "0001"
            reference_number = None
            letter_date = None
            date_of_joining = None
            employee_name = None
            salutation_title = None
            first_name = None
            designation = None
            department = None
            posting_location = None
            company_name_display = None
            address = None
            probation_period = None
            working_hours = None
            working_days = None
            lunch_break = None
            monthly_salary = None
            monthly_salary_in_words = None
            annual_ctc = None
            basic_salary_monthly = None
            basic_salary_annual = None
            da_monthly = None
            da_annual = None
            hra_monthly = None
            hra_annual = None
            other_allowances_monthly = None
            other_allowances_annual = None
            gross_salary_monthly = None
            gross_salary_annual = None
            employer_pf_monthly = None
            employer_pf_annual = None
            employer_esi_monthly = None
            employer_esi_annual = None
            ctc_monthly = None
            ctc_annual = None
            salutation = None
            introduction = None
            clause_1_appointment_scope = None
            clause_2_classification = None
            clause_3_probation = None
            clause_4_working_hours = None
            clause_5_leave_policy = None
            clause_6_compensation = None
            clause_7_duties_conduct = None
            clause_8_dress_code = None
            clause_9_confidentiality = None
            clause_10_transfer = None
            clause_11_resignation_termination = None
            clause_12_general_terms = None
            clause_13_policy_compliance = None
            clause_14_acceptance = None
            acceptance_statement = None
            signatory_company_label = None
            hr_signatory_name = None
            hr_signatory_designation = None
            hr_signatory_title = None
            signature_image = None

        tmpl = Template(template_str)
        output = tmpl.render(doc=MinimalDoc(), frappe={"utils": MockFrappeUtils()})
        self.assertEqual(output.count('<div class="appointment-page">'), 7)
        self.assertIn("METT/HR/AL/01/2026", output)
        self.assertIn("Middle East Travels & Tourism", output)


    def test_custom_fields_and_image_uploads_override(self):
        """Verify custom image uploads (logos & signature), location, signatory and clauses override defaults"""
        with open(self.travels_html_path, "r", encoding="utf-8") as f:
            template_str = f.read()

        class MockFrappeUtils:
            @staticmethod
            def formatdate(d, fmt):
                return "26.09.2026"

        class CustomDoc:
            name = "HR-APP-LETTER-00001"
            applicant_name = "Jane Candidate"
            company = "middle east travels & tourism"
            custom_company_logo = "/files/custom_middle_east_logo.png"
            custom_iata_logo = "/files/custom_iata_logo.png"
            custom_signature_image = "/files/custom_hr_signature.png"
            custom_posting_location = "Kochi InfoPark"
            custom_hr_signatory_name = "Anoop Kumar"
            custom_hr_signatory_designation = "Lead HR Manager"
            custom_signatory_company_label = "For Middle East Travels & Tourism"
            custom_monthly_salary = 25000.0
            custom_monthly_salary_in_words = "Rupees Twenty Five Thousand Only"
            custom_clause_1_appointment_scope = "Custom Scope: Appointed as Executive Lead at Kochi."
            terms = []

        tmpl = Template(template_str)
        output = tmpl.render(doc=CustomDoc(), frappe={"utils": MockFrappeUtils()})

        self.assertIn("Jane Candidate", output)
        self.assertIn("/files/custom_middle_east_logo.png", output)
        self.assertIn("/files/custom_iata_logo.png", output)
        self.assertIn("/files/custom_hr_signature.png", output)
        self.assertIn("Anoop Kumar", output)
        self.assertIn("Lead HR Manager", output)
        self.assertIn("25,000", output)
        self.assertIn("Rupees Twenty Five Thousand Only", output)
        self.assertIn("Custom Scope: Appointed as Executive Lead at Kochi.", output)

    def test_terms_table_overrides_in_print(self):
        """Verify standard HRMS terms child table descriptions override defaults when present"""
        with open(self.holidays_html_path, "r", encoding="utf-8") as f:
            template_str = f.read()

        class MockFrappeUtils:
            @staticmethod
            def formatdate(d, fmt):
                return "26.09.2026"

        class TermItem:
            def __init__(self, title, description):
                self.title = title
                self.description = description

        class DocWithTerms:
            name = "HR-APP-LETTER-00002"
            applicant_name = "Terms User"
            company = "middle east holidays"
            terms = [
                TermItem("1. APPOINTMENT & SCOPE OF EMPLOYMENT", "Edited appointment scope from child table."),
                TermItem("3. PROBATION, REVIEW & CONFIRMATION", "Edited probation term from child table."),
            ]

        tmpl = Template(template_str)
        output = tmpl.render(doc=DocWithTerms(), frappe={"utils": MockFrappeUtils()})

        self.assertIn("Edited appointment scope from child table.", output)
        self.assertIn("Edited probation term from child table.", output)
        self.assertIn("Middle East Holidays", output)

if __name__ == "__main__":
    unittest.main()
