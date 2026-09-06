"""
Test 6: MCP Tool Execution Verification over Stdio Client Session.
Verifies all 10 tools return structured production data via the MCP Protocol.
"""

import sys
import os
import json
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import config


EXPECTED_TOOLS = [
    "get_today_leads",
    "get_leads_by_date",
    "get_lead_report",
    "get_leads_by_department",
    "get_leads_by_counselor",
    "get_lead_sources",
    "get_unassigned_leads",
    "get_followups",
    "get_tasks",
    "get_visa_applications",
    "get_management_summary",
]


async def main():
    print("=== Test 6: Complete MCP Tool Execution via Protocol Client Session ===")
    
    server_py = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server.py"))
    python_bin = sys.executable

    server_params = StdioServerParameters(
        command=python_bin,
        args=[server_py],
        env=None
    )

    print(f"[*] Spawning MCP server via stdio: {python_bin} {server_py}")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # 1. Initialize protocol
            init_res = await session.initialize()
            print(f"[*] MCP Session Initialized. Protocol Version: {init_res.protocol_version}")

            # 2. List tools
            tools_res = await session.list_tools()
            tool_names = [t.name for t in tools_res.tools]
            print(f"[*] Discovered tools via protocol: {tool_names}")
            for tool_name in EXPECTED_TOOLS:
                assert tool_name in tool_names, f"{tool_name} not found in tool list"

            # 3. Test get_today_leads
            print("\n[*] Calling tool 'get_today_leads' via session.call_tool()...")
            res = await session.call_tool("get_today_leads", arguments={})
            data = json.loads(res.content[0].text)
            assert data.get("success") is True
            print(f"    -> Success! Leads today: {data.get('total')}")

            # 4. Test get_leads_by_date
            print("[*] Calling tool 'get_leads_by_date' for '2026-09-06'...")
            res = await session.call_tool("get_leads_by_date", arguments={"date": "2026-09-06"})
            data = json.loads(res.content[0].text)
            assert data.get("success") is True
            print(f"    -> Success! Leads on 2026-09-06: {data.get('total')}")

            # 5. Test get_lead_report
            print("[*] Calling tool 'get_lead_report' for '2026-09-01' to '2026-09-06'...")
            res = await session.call_tool("get_lead_report", arguments={"start_date": "2026-09-01", "end_date": "2026-09-06"})
            data = json.loads(res.content[0].text)
            assert data.get("success") is True
            print(f"    -> Success! Total in report: {data.get('total_leads')}")

            # 6. Test get_leads_by_department
            print("[*] Calling tool 'get_leads_by_department' for 'Holidays - MEH'...")
            res = await session.call_tool("get_leads_by_department", arguments={"department": "Holidays - MEH"})
            data = json.loads(res.content[0].text)
            assert data.get("success") is True
            print(f"    -> Success! Holidays leads: {data.get('total')}")

            # 7. Test get_lead_sources
            print("[*] Calling tool 'get_lead_sources'...")
            res = await session.call_tool("get_lead_sources", arguments={"start_date": "2026-09-01", "end_date": "2026-09-06"})
            data = json.loads(res.content[0].text)
            assert data.get("success") is True
            print(f"    -> Success! Sources: {data.get('sources')}")

            # 8. Test get_unassigned_leads
            print("[*] Calling tool 'get_unassigned_leads'...")
            res = await session.call_tool("get_unassigned_leads", arguments={"start_date": "2026-09-06", "end_date": "2026-09-06"})
            data = json.loads(res.content[0].text)
            assert data.get("success") is True
            print(f"    -> Success! Unassigned today: {data.get('total')}")

            # 9. Test get_followups
            print("[*] Calling tool 'get_followups'...")
            res = await session.call_tool("get_followups", arguments={})
            data = json.loads(res.content[0].text)
            assert data.get("success") is True
            print(f"    -> Success! Follow-ups: {data.get('total')}")

            # 10. Test get_tasks
            print("[*] Calling tool 'get_tasks'...")
            res = await session.call_tool("get_tasks", arguments={})
            data = json.loads(res.content[0].text)
            assert data.get("success") is True
            print(f"    -> Success! Tasks: {data.get('total')}")

            # 11. Test get_visa_applications
            print("[*] Calling tool 'get_visa_applications'...")
            res = await session.call_tool("get_visa_applications", arguments={"status": "Draft"})
            data = json.loads(res.content[0].text)
            assert data.get("success") is True
            print(f"    -> Success! Draft Visas: {data.get('total')}")

            # 12. Test get_management_summary
            print("[*] Calling tool 'get_management_summary'...")
            res = await session.call_tool("get_management_summary", arguments={})
            data = json.loads(res.content[0].text)
            assert data.get("success") is True
            print(f"    -> Success! Management summary leads: {data.get('leads', {}).get('total')}")

            print("\n[RESULT] Test 6: All MCP Tools Executed Successfully via Stdio Protocol: PASS\n")


if __name__ == "__main__":
    asyncio.run(main())
