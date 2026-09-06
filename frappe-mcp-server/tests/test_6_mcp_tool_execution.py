"""
Test 6: MCP Tool Execution Verification over Stdio Client Session.
Verifies get_today_leads returns structured production lead data via the MCP Server.
"""

import sys
import os
import json
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import config


async def main():
    print("=== Test 6: MCP Tool Execution via Protocol Client Session ===")
    
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
            assert "get_today_leads" in tool_names, "get_today_leads not found in tool list"

            # 3. Call tool
            print("[*] Calling tool 'get_today_leads' via session.call_tool()...")
            tool_call_res = await session.call_tool("get_today_leads", arguments={})
            assert len(tool_call_res.content) > 0, "Empty tool result content"
            
            raw_text = tool_call_res.content[0].text
            result = json.loads(raw_text)
            print(f"[*] Tool execution completed. Success flag: {result.get('success')}")

            if config.is_configured:
                assert result.get("success") is True, f"Tool call failed: {result}"
                assert "leads" in result
                assert "total" in result
                print(f"[*] Live production leads retrieved via MCP tool: {result['total']}")
                if result["leads"]:
                    first_lead = result["leads"][0]
                    print(f"[*] Sample Lead: Name={first_lead.get('name')}, Customer={first_lead.get('customer_name')}, Dept={first_lead.get('department')}")
                print("\n[RESULT] Test 6: MCP Tool Execution via Protocol: PASS\n")
            else:
                print(f"[*] Credentials not set. Result: {result.get('error')}")
                assert result.get("success") is False
                assert "authentication" in result.get("error", "").lower()
                print("[*] Controlled error handling verified via MCP protocol.")
                print("\n[RESULT] Test 6 (Protocol Session Controlled Error): PASS\n")


if __name__ == "__main__":
    asyncio.run(main())
