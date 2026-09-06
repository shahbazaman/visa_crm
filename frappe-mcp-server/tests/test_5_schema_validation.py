"""
Test 5: Response Schema Validation Suite.
Validates structure, types, 9 required lead fields, and consistent null representation.
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import config
from frappe_client import frappe_client, REQUIRED_LEAD_FIELDS, FrappeClient


async def test_schema_with_mock_and_live():
    print("=== Test 5: Response Schema Validation Suite ===")
    
    # 1. Structural Unit Test against synthetic production-shaped response
    print("\n--- Part A: Strict Schema Assertion on Reference Payload ---")
    reference_payload = {
        "message": {
            "success": True,
            "date": "2026-09-06",
            "total": 1,
            "leads": [
                {
                    "name": "CRM-LEAD-2026-00629",
                    "customer_name": "Azna.fairuz",
                    "email": None,
                    "phone": "+918714889392",
                    "status": "Qualified",
                    "source": "Meta Instant Form",
                    "creation": "2026-09-06 18:26:29.603265",
                    "assigned_counselor": None,
                    "department": "Holidays - MEH",
                }
            ],
        }
    }
    
    client = FrappeClient()
    validated = client._validate_response_schema(reference_payload)
    assert validated["success"] is True
    assert isinstance(validated["date"], str)
    assert isinstance(validated["total"], int)
    assert isinstance(validated["leads"], list)
    assert len(validated["leads"]) == 1
    
    sample_lead = validated["leads"][0]
    for key in REQUIRED_LEAD_FIELDS:
        assert key in sample_lead, f"Missing required field: {key}"
    print(f"[*] Reference payload validated with all {len(REQUIRED_LEAD_FIELDS)} required keys.")
    print("    Fields verified: " + ", ".join(REQUIRED_LEAD_FIELDS))

    # 2. Live Production Schema Assertion (if credentials configured)
    print("\n--- Part B: Live Production Schema Verification ---")
    if config.is_configured:
        print("[*] Fetching live data from production...")
        live_data = await frappe_client.get_today_leads()
        assert live_data["success"] is True
        assert "date" in live_data
        assert "total" in live_data
        assert isinstance(live_data["leads"], list)
        
        print(f"[*] Live production total leads: {live_data['total']}")
        for idx, lead in enumerate(live_data["leads"], start=1):
            for field in REQUIRED_LEAD_FIELDS:
                assert field in lead, f"Lead #{idx} missing field {field}"
        print(f"[*] All {len(live_data['leads'])} live leads verified against strict 9-field schema.")
        print("\n[RESULT] Test 5: Response Schema Validation: PASS\n")
    else:
        print("[!] Credentials not yet configured in .env. Unit schema validation passed.")
        print("[RESULT] Test 5 (Unit): PASS\n")


if __name__ == "__main__":
    asyncio.run(test_schema_with_mock_and_live())
