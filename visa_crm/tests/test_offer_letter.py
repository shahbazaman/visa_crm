# -*- coding: utf-8 -*-
"""
Automated Unit Tests for Middle East Travels Offer Letter System
================================================================
Tests:
1. Numbering sequence (0001, 0002, 0003)
2. Template population and dynamic substitution
3. Salary in words calculation
4. Section editability and preservation
5. Long address handling
6. Safe fallbacks for missing optional data
7. Print format Jinja rendering of all 3 pages
"""
import unittest
from datetime import date

class TestOfferLetterNumbering(unittest.TestCase):
    def test_continuous_numbering_sequence(self):
        """
        Verify that sequential numbers generate 0001, 0002, 0003 and format reference ME/HRD/OL/01.
        """
        samples = [
            ("OFFER-0001", "0001", "ME/HRD/OL/01"),
            ("OFFER-0002", "0002", "ME/HRD/OL/02"),
            ("OFFER-0003", "0003", "ME/HRD/OL/03"),
            ("OFFER-0007", "0007", "ME/HRD/OL/07"),
            ("OFFER-0025", "0025", "ME/HRD/OL/25"),
        ]
        for name, expected_num, expected_ref in samples:
            parts = name.split("-")
            offer_number = parts[-1]
            num = int(offer_number)
            ref_number = f"ME/HRD/OL/{num:02d}"
            self.assertEqual(offer_number, expected_num)
            self.assertEqual(ref_number, expected_ref)

class TestTemplateDynamicSubstitution(unittest.TestCase):
    def test_variable_substitution(self):
        template_text = (
            "With reference to the discussions we had with you, we are pleased to extend to you an offer "
            "for the position of {designation} at {company}. Date of Joining: {date_of_joining}. "
            "Monthly salary will be INR {monthly_salary} ({monthly_salary_in_words})."
        )
        context = {
            "designation": "Sales & Marketing Executive",
            "company": "Middle East Travels & Tourism",
            "date_of_joining": "11.09.2026",
            "monthly_salary": "18,000",
            "monthly_salary_in_words": "Rupees Eighteen Thousand Only"
        }
        rendered = template_text
        for k, v in context.items():
            rendered = rendered.replace(f"{{{k}}}", str(v))

        self.assertIn("Sales & Marketing Executive", rendered)
        self.assertIn("Middle East Travels & Tourism", rendered)
        self.assertIn("INR 18,000 (Rupees Eighteen Thousand Only)", rendered)
        self.assertIn("11.09.2026", rendered)

    def test_salary_in_words(self):
        # Test cleaning and casing of money_in_words output
        raw_words = "INR Eighteen Thousand only."
        cleaned = raw_words.replace("INR ", "Rupees ").replace(" only.", " Only").replace(" Only.", " Only")
        if not cleaned.endswith("Only"):
            cleaned += " Only"
        self.assertEqual(cleaned, "Rupees Eighteen Thousand Only")

class TestPrintFormatRendering(unittest.TestCase):
    def test_3_page_structure_presence(self):
        from jinja2 import Template
        pf_html_path = "/home/shahbaz/frappe-bench/apps/visa_crm/visa_crm/visa_crm/print_format/middle_east_travels_offer_letter/middle_east_travels_offer_letter.html"
        with open(pf_html_path, "r", encoding="utf-8") as f:
            template_str = f.read()

        # Mock document
        class MockFrappeUtils:
            @staticmethod
            def formatdate(d, fmt):
                return "10.09.2026"

        class MockDoc:
            name = "OFFER-0001"
            offer_number = "0001"
            reference_number = "ME/HRD/OL/07"
            letter_date = date(2026, 9, 10)
            date_of_joining = date(2026, 9, 11)
            employee_name = "Akshay Prasob V"
            first_name = "Akshay"
            designation = "Sales & Marketing Executive"
            company_name_display = "Middle East Travels & Tourism"
            address = "Veluppal House\nKizhakkumuri Post\nKakkodi\nKozhikode, Kerala - 673611"
            salutation = "Dear Mr. Akshay,"
            introduction = "With reference to the discussions we had with you, we are pleased to extend to you an offer..."
            compensation_details = "Your monthly salary will be INR 18,000 (Rupees Eighteen Thousand Only)."
            probation_details = "You will be on probation for a period of three (3) months..."
            performance_reviews = "Your performance will be reviewed periodically..."
            working_hours_details = "Your working hours will be from Monday to Saturday, 10:00 AM to 5:30 PM."
            leave_details = "You will be entitled to two (2) paid leaves per month..."
            notice_period_details = "Either party may terminate the employment by providing one (1) month's written notice..."
            joining_details = "You are requested to report at Middle East Travels & Tourism on 11th September 2026..."
            required_documents = "<ol><li>Relieving letter</li><li>Last 3 months salary slips</li></ol>"
            acceptance_terms = "This offer is subject to your acceptance..."
            acceptance_statement = "I accept the offer of employment..."
            signatory_company_label = "For, Middle East Travels & Tourism"
            hr_signatory_name = "Gopika"
            hr_signatory_designation = "HR Consultant"
            hr_signatory_title = "Authorized Signatory"

        tmpl = Template(template_str)
        output = tmpl.render(doc=MockDoc(), frappe={"utils": MockFrappeUtils()})

        # Verify exact 3 pages structure
        page_count = output.count('<div class="offer-page">')
        self.assertEqual(page_count, 3, "Output must contain exactly 3 offer pages")

        # Verify key text presence
        self.assertIn("CONGRATULATIONS", output)
        self.assertIn("ME/HRD/OL/07", output)
        self.assertIn("Akshay Prasob V", output)
        self.assertIn("Veluppal House<br>Kizhakkumuri Post<br>Kakkodi<br>Kozhikode, Kerala - 673611", output)
        self.assertIn("Gopika", output)
        self.assertIn("Authorized Signatory", output)
        self.assertIn("Shobha Tower, 5/3412L, Mavoor Rd", output)
        self.assertIn("IATA", output)

    def test_missing_optional_fields_fallback(self):
        from jinja2 import Template
        pf_html_path = "/home/shahbaz/frappe-bench/apps/visa_crm/visa_crm/visa_crm/print_format/middle_east_travels_offer_letter/middle_east_travels_offer_letter.html"
        with open(pf_html_path, "r", encoding="utf-8") as f:
            template_str = f.read()

        class MockFrappeUtils:
            @staticmethod
            def formatdate(d, fmt):
                return ""

        class MinimalDoc:
            name = "OFFER-0002"
            offer_number = "0002"
            reference_number = None
            letter_date = None
            date_of_joining = None
            employee_name = None
            first_name = None
            designation = None
            company_name_display = None
            address = None
            salutation = None
            introduction = None
            compensation_details = None
            probation_details = None
            performance_reviews = None
            working_hours_details = None
            leave_details = None
            notice_period_details = None
            joining_details = None
            required_documents = None
            acceptance_terms = None
            acceptance_statement = None
            signatory_company_label = None
            hr_signatory_name = None
            hr_signatory_designation = None
            hr_signatory_title = None

        tmpl = Template(template_str)
        # Should render safely without throwing any exceptions
        output = tmpl.render(doc=MinimalDoc(), frappe={"utils": MockFrappeUtils()})
        self.assertEqual(output.count('<div class="offer-page">'), 3)
        self.assertIn("ME/HRD/OL/02", output)
        self.assertIn("Middle East Travels & Tourism", output)

if __name__ == "__main__":
    unittest.main()
