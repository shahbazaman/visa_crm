"""
Test 1: Verify MCP Server Starts & Initializes All 10 Tools Cleanly.
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from server import mcp


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
]


async def main():
    print("=== Test 1: MCP Server Startup & Tool Registration Verification ===")
    
    assert mcp.name == "frappe-crm", f"Unexpected server name: {mcp.name}"
    print(f"[*] MCP Server instance initialized: {mcp.name}")

    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    print(f"[*] Total registered tools: {len(tool_names)}")
    print(f"[*] Registered tools found: {tool_names}")

    for exp in EXPECTED_TOOLS:
        assert exp in tool_names, f"Tool '{exp}' is not registered in MCP Server!"
        tool_def = next(t for t in tools if t.name == exp)
        assert tool_def.description, f"Tool '{exp}' lacks a description!"
        print(f"    [+] {exp}: OK (Description verified)")
    
    print("\n[RESULT] Test 1: MCP Server Startup & All 10 Tools Registered: PASS\n")


if __name__ == "__main__":
    asyncio.run(main())
