"""
Test 1: Verify MCP Server Starts & Initializes Tools Cleanly.
"""

import sys
import os
import asyncio

# Ensure parent directory is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from server import mcp


async def main():
    print("=== Test 1: MCP Server Startup Verification ===")
    
    # Check server metadata
    assert mcp.name == "frappe-crm", f"Unexpected server name: {mcp.name}"
    print(f"[*] MCP Server instance initialized: {mcp.name}")

    # Inspect registered tools
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    print(f"[*] Registered tools found: {tool_names}")

    assert "get_today_leads" in tool_names, "Tool 'get_today_leads' not registered!"
    
    # Verify tool description matches requirements
    tool_def = next(t for t in tools if t.name == "get_today_leads")
    assert "CRM Lead" in tool_def.description, "Tool description does not describe CRM Lead records"
    assert "read-only" in tool_def.description.lower(), "Tool description does not indicate read-only"
    print(f"[*] Tool definition verified: {tool_def.name}")
    print(f"    Description: {tool_def.description}")
    
    print("\n[RESULT] Test 1: MCP Server Startup: PASS\n")


if __name__ == "__main__":
    asyncio.run(main())
