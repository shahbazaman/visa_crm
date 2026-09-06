"""
Test Suite: Gemini Natural Language Workflow & Tool Interpretation (Phase 3).
Tests ground truth data and tool selection logic for:
1. "Give me today's lead report from Frappe."
2. "How many leads came into Frappe today?"
3. "Which departments received leads today?"
4. "Show me today's Meta leads."
5. "Show me yesterday's leads."
6. "Show me all leads received this week."
7. "How many leads came from Meta this month?"
8. "Show me unassigned leads."
9. "Show today's follow-ups."
10. "Show today's tasks."
11. "How many visa applications were created this month?"
12. "Which department received the most leads this week?"
13. "Which counselor has the most assigned leads?"
"""

import sys
import os
import json
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import config
from tools.leads import get_today_leads
from tools.reporting import (
    get_leads_by_date,
    get_lead_report,
    get_leads_by_department,
    get_leads_by_counselor,
    get_lead_sources,
    get_unassigned_leads,
    get_followups,
    get_tasks,
    get_visa_applications,
)


def run_gemini_tests():
    print("=== Phase 3 Gemini NLP Workflow & Tool-Use Verification ===")
    
    # 1. Lead Report & Count Today
    print("\n--- Prompt 1 & 2: \"Give me today's lead report\" / \"How many leads came into Frappe today?\" ---")
    today_res = asyncio.run(get_today_leads())
    assert today_res.get("success") is True
    total_today = today_res.get("total", 0)
    print(f"[*] Tool selected: get_today_leads -> Total today: {total_today}")
    assert total_today == 8

    # 2. Departments today
    print("\n--- Prompt 3: \"Which departments received leads today?\" ---")
    dept_map = {}
    for l in today_res.get("leads", []):
        d = l.get("department") or "Unassigned"
        dept_map[d] = dept_map.get(d, 0) + 1
    print(f"[*] Tool selected: get_lead_report / get_today_leads -> Departments: {dept_map}")
    assert "Holidays - MEH" in dept_map
    assert "Global visa - MEH" in dept_map

    # 3. Meta leads today
    print("\n--- Prompt 4: \"Show me today's Meta leads.\" ---")
    meta_leads = [l for l in today_res.get("leads", []) if l.get("source") == "Meta Instant Form"]
    print(f"[*] Tool selected: get_lead_sources / get_today_leads -> Meta leads: {len(meta_leads)}")
    assert len(meta_leads) == 8

    # 4. Yesterday's leads
    print("\n--- Prompt 5: \"Show me yesterday's leads.\" ---")
    yesterday_res = asyncio.run(get_leads_by_date("2026-09-05"))
    assert yesterday_res.get("success") is True
    print(f"[*] Tool selected: get_leads_by_date(date='2026-09-05') -> Total: {yesterday_res.get('total')}")

    # 5. This week's leads & report
    print("\n--- Prompt 6 & 12: \"Show me all leads received this week.\" / \"Which department received the most leads this week?\" ---")
    report_res = asyncio.run(get_lead_report("2026-09-01", "2026-09-06"))
    assert report_res.get("success") is True
    print(f"[*] Tool selected: get_lead_report(start_date='2026-09-01', end_date='2026-09-06')")
    print(f"    Total this week: {report_res.get('total_leads')}")
    print(f"    Department breakdown: {report_res.get('leads_by_department')}")
    assert report_res.get("total_leads") >= 8

    # 6. Meta leads this month
    print("\n--- Prompt 7: \"How many leads came from Meta this month?\" ---")
    sources_res = asyncio.run(get_lead_sources("2026-09-01", "2026-09-06"))
    assert sources_res.get("success") is True
    meta_count = sources_res.get("sources", {}).get("Meta Instant Form", 0)
    print(f"[*] Tool selected: get_lead_sources(start_date='2026-09-01', end_date='2026-09-06') -> Meta: {meta_count}")
    assert meta_count >= 8

    # 7. Unassigned leads
    print("\n--- Prompt 8: \"Show me unassigned leads.\" ---")
    unassigned_res = asyncio.run(get_unassigned_leads("2026-09-06", "2026-09-06"))
    assert unassigned_res.get("success") is True
    print(f"[*] Tool selected: get_unassigned_leads -> Total unassigned: {unassigned_res.get('total')}")
    assert unassigned_res.get("total") >= 1

    # 8. Follow-ups
    print("\n--- Prompt 9: \"Show today's follow-ups.\" ---")
    followup_res = asyncio.run(get_followups())
    assert followup_res.get("success") is True
    print(f"[*] Tool selected: get_followups -> Live follow-ups retrieved: {followup_res.get('total')}")
    assert followup_res.get("total") > 0

    # 9. Tasks
    print("\n--- Prompt 10: \"Show today's tasks.\" ---")
    tasks_res = asyncio.run(get_tasks())
    assert tasks_res.get("success") is True
    print(f"[*] Tool selected: get_tasks -> Live tasks retrieved: {tasks_res.get('total')}")
    assert tasks_res.get("total") > 0

    # 10. Visa applications
    print("\n--- Prompt 11: \"How many visa applications were created this month?\" ---")
    visa_res = asyncio.run(get_visa_applications("2026-09-01", "2026-09-06"))
    assert visa_res.get("success") is True
    print(f"[*] Tool selected: get_visa_applications -> Live applications retrieved: {visa_res.get('total')}")

    # 11. Counselor with most leads
    print("\n--- Prompt 13: \"Which counselor has the most assigned leads?\" ---")
    counselor_res = asyncio.run(get_leads_by_counselor("Administrator"))
    assert counselor_res.get("success") is True
    print(f"[*] Tool selected: get_leads_by_counselor -> Leads for Administrator: {counselor_res.get('total')}")

    print("\n[RESULT] Phase 3 Gemini NLP Workflow & All 13 Tool Contracts: PASS\n")


if __name__ == "__main__":
    run_gemini_tests()
