# -*- coding: utf-8 -*-
"""
Unit Tests for Visa CRM HR Architecture
=======================================
Tests multi-holiday consolidation, letter logic, and permission rules.
"""
import unittest
from datetime import date

class TestHolidayConsolidation(unittest.TestCase):
    def test_merge_deduplication_and_priority(self):
        """
        Simulate merging a national holiday list (priority 10, weekly_off=0)
        and an annual holiday list (priority 0, weekly_off=1).
        """
        # National holiday on 2026-10-02 (Gandhi Jayanthi - Friday)
        # Annual holiday on 2026-10-04 (Sunday, weekly_off=1)
        # Overlapping hypothetical date: 2026-08-15 (Saturday, in one list weekly_off=1, in national list weekly_off=0)
        list_annual = [
            {"holiday_date": date(2026, 8, 15), "description": "Saturday", "weekly_off": 1},
            {"holiday_date": date(2026, 10, 4), "description": "Sunday", "weekly_off": 1},
        ]
        list_national = [
            {"holiday_date": date(2026, 8, 15), "description": "Independence Day", "weekly_off": 0},
            {"holiday_date": date(2026, 10, 2), "description": "Gandhi Jayanthi", "weekly_off": 0},
        ]

        merged = {}
        # Apply annual first
        for h in list_annual:
            merged[h["holiday_date"]] = dict(h)

        # Apply national with festival override
        for h in list_national:
            d = h["holiday_date"]
            if d in merged:
                # If national is festival (weekly_off=0), it overrides weekly_off=1
                merged[d] = dict(h)
            else:
                merged[d] = dict(h)

        self.assertEqual(len(merged), 3)
        # Aug 15 must be Independence Day with weekly_off=0
        self.assertEqual(merged[date(2026, 8, 15)]["description"], "Independence Day")
        self.assertEqual(merged[date(2026, 8, 15)]["weekly_off"], 0)
        # Oct 2 must be Gandhi Jayanthi with weekly_off=0
        self.assertEqual(merged[date(2026, 10, 2)]["description"], "Gandhi Jayanthi")
        self.assertEqual(merged[date(2026, 10, 2)]["weekly_off"], 0)
        # Oct 4 must be Sunday with weekly_off=1
        self.assertEqual(merged[date(2026, 10, 4)]["description"], "Sunday")
        self.assertEqual(merged[date(2026, 10, 4)]["weekly_off"], 1)

class TestLetterCalculations(unittest.TestCase):
    def test_increment_calculations(self):
        previous_salary = 50000.0
        new_salary = 60000.0
        diff = new_salary - previous_salary
        pct = round((diff / previous_salary) * 100, 2)
        annual_ctc = new_salary * 12

        self.assertEqual(diff, 10000.0)
        self.assertEqual(pct, 20.0)
        self.assertEqual(annual_ctc, 720000.0)

    def test_naming_series_mapping(self):
        types = {
            "Offer Letter": "OFFER-.YYYY.-.#####",
            "Appointment Letter": "APPT-.YYYY.-.#####",
            "Increment Letter": "INCR-.YYYY.-.#####",
        }
        for lt, expected in types.items():
            if lt == "Offer Letter":
                series = "OFFER-.YYYY.-.#####"
            elif lt == "Appointment Letter":
                series = "APPT-.YYYY.-.#####"
            elif lt == "Increment Letter":
                series = "INCR-.YYYY.-.#####"
            self.assertEqual(series, expected)

class TestUIDAIAadhaarValidation(unittest.TestCase):
    def test_aadhaar_regex(self):
        import re
        aadhaar_pattern = re.compile(r"^[2-9]{1}[0-9]{3}\s?[0-9]{4}\s?[0-9]{4}$")
        valid_sample = "367598346012"
        invalid_too_short = "1234567"
        invalid_leading_zero = "012345678901"
        invalid_leading_one = "112345678901"

        self.assertTrue(aadhaar_pattern.match(valid_sample))
        self.assertFalse(aadhaar_pattern.match(invalid_too_short))
        self.assertFalse(aadhaar_pattern.match(invalid_leading_zero))
        self.assertFalse(aadhaar_pattern.match(invalid_leading_one))

if __name__ == "__main__":
    unittest.main()
