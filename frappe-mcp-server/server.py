"""
Frappe CRM Model Context Protocol (MCP) Server.
Connects Google Gemini to production Frappe CRM via controlled read-only reporting APIs.
Supports both local Stdio transport and remote SSE transport with Bearer token authentication.
"""

import argparse
import sys
from typing import Optional
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from config import config
from tools.leads import get_today_leads as fetch_today_leads
from tools.reporting import (
    get_leads_by_date as fetch_leads_by_date,
    get_lead_report as fetch_lead_report,
    get_leads_by_department as fetch_leads_by_department,
    get_leads_by_counselor as fetch_leads_by_counselor,
    get_lead_sources as fetch_lead_sources,
    get_unassigned_leads as fetch_unassigned_leads,
    get_followups as fetch_followups,
    get_tasks as fetch_tasks,
    get_visa_applications as fetch_visa_applications,
    get_management_summary as fetch_management_summary,
)


# Initialize MCPServer instance
mcp = MCPServer(
    name="frappe-crm",
    instructions=(
        "You are an assistant connected to the Visa CRM Frappe production system. "
        "Use the provided read-only reporting tools to query real-time CRM leads, departments, "
        "counselors, sources, reports, follow-ups, tasks, visa applications, and management briefings. "
        "Always present accurate live data and do not fabricate information. "
        "Interprets natural-language date questions into explicit YYYY-MM-DD format using Frappe server timezone."
    ),
)


# =============================================================================
# 1. LEAD TOOLS
# =============================================================================

@mcp.tool(
    name="get_today_leads",
    description="Returns today's CRM Lead records from production Frappe CRM. Use when the user specifically asks for leads received today.",
)
async def get_today_leads() -> dict:
    """Returns today's CRM Lead records from the production Visa CRM Frappe instance."""
    return await fetch_today_leads()


@mcp.tool(
    name="get_leads_by_date",
    description="Returns CRM leads created on a specific calendar date (date in YYYY-MM-DD format). Use for single-day queries such as 'yesterday', 'leads on September 5'.",
)
async def get_leads_by_date(date: str) -> dict:
    """Returns CRM leads created on a specific date (YYYY-MM-DD)."""
    return await fetch_leads_by_date(date)


@mcp.tool(
    name="get_lead_report",
    description=(
        "Returns an aggregated CRM lead report for a date range (start_date and end_date in YYYY-MM-DD format). "
        "Includes total leads, breakdown by department, breakdown by source, breakdown by status, "
        "and assigned vs unassigned distribution. Ideal for weekly/monthly sales reports."
    ),
)
async def get_lead_report(start_date: str, end_date: str) -> dict:
    """Returns an aggregated CRM lead report for a date range."""
    return await fetch_lead_report(start_date, end_date)


@mcp.tool(
    name="get_leads_by_department",
    description="Returns CRM leads belonging to a specific department (e.g. 'Holidays - MEH', 'Global visa - MEH', 'Holidays').",
)
async def get_leads_by_department(department: str) -> dict:
    """Returns CRM leads belonging to a specific department."""
    return await fetch_leads_by_department(department)


@mcp.tool(
    name="get_leads_by_counselor",
    description="Returns CRM leads assigned to a specific counselor or user identifier (e.g. 'Administrator', 'admin@middleeast.com').",
)
async def get_leads_by_counselor(counselor: str) -> dict:
    """Returns CRM leads assigned to a specific counselor."""
    return await fetch_leads_by_counselor(counselor)


@mcp.tool(
    name="get_lead_sources",
    description="Returns lead acquisition counts aggregated by source channel (e.g. Meta Instant Form, WhatsApp, Website) for an optional date range (YYYY-MM-DD).",
)
async def get_lead_sources(
    start_date: Optional[str] = None, end_date: Optional[str] = None
) -> dict:
    """Returns lead acquisition counts aggregated by source channel."""
    return await fetch_lead_sources(start_date, end_date)


@mcp.tool(
    name="get_unassigned_leads",
    description="Returns CRM leads where counselor/owner assignment is currently missing or pending, for an optional date range (YYYY-MM-DD).",
)
async def get_unassigned_leads(
    start_date: Optional[str] = None, end_date: Optional[str] = None
) -> dict:
    """Returns CRM leads where counselor assignment is missing or pending."""
    return await fetch_unassigned_leads(start_date, end_date)


# =============================================================================
# 2. OPERATIONAL TOOLS (FOLLOWUPS, TASKS & VISAS)
# =============================================================================

@mcp.tool(
    name="get_followups",
    description="Returns controlled follow-up and reminder records linked to CRM leads for an optional date range (YYYY-MM-DD). Use for questions about follow-up calls and pending reminders.",
)
async def get_followups(
    start_date: Optional[str] = None, end_date: Optional[str] = None
) -> dict:
    """Returns controlled follow-up and reminder records linked to CRM leads."""
    return await fetch_followups(start_date, end_date)


@mcp.tool(
    name="get_tasks",
    description="Returns controlled task records linked to CRM leads or employees, with optional date range (YYYY-MM-DD) and optional assigned_employee filter.",
)
async def get_tasks(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    assigned_employee: Optional[str] = None,
) -> dict:
    """Returns controlled task records linked to CRM leads or employees."""
    return await fetch_tasks(start_date, end_date, assigned_employee)


@mcp.tool(
    name="get_visa_applications",
    description="Returns controlled Visa Application reporting data, with optional date range (YYYY-MM-DD) and optional status filter (e.g. 'Draft', 'Submitted', 'Approved', 'Rejected').",
)
async def get_visa_applications(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status: Optional[str] = None,
) -> dict:
    """Returns controlled Visa Application reporting data."""
    return await fetch_visa_applications(start_date, end_date, status)


# =============================================================================
# 3. EXECUTIVE BI DASHBOARD TOOL
# =============================================================================

@mcp.tool(
    name="get_management_summary",
    description=(
        "Returns a comprehensive executive management briefing combining lead volumes, department breakdowns, "
        "source distributions, counselor assignment backlog, active follow-ups, visa conversions, "
        "and items requiring managerial attention. Ideal for 'Give me today's management summary' or 'What needs attention today?'."
    ),
)
async def get_management_summary(date: Optional[str] = None) -> dict:
    """Returns a comprehensive executive management briefing."""
    return await fetch_management_summary(date)


# =============================================================================
# HTTP & SSE INFRASTRUCTURE
# =============================================================================

class MCPAuthMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware for remote incoming MCP requests.
    Validates Authorization Bearer token against MCP_AUTH_TOKEN when configured.
    Health check (/health) is always public.
    """

    async def dispatch(self, request, call_next):
        if request.url.path in ("/health", "/health/") or request.method == "OPTIONS":
            return await call_next(request)

        expected_token = config.mcp_auth_token
        if expected_token:
            auth_header = request.headers.get("Authorization", "")
            token = None
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
            elif auth_header.startswith("token "):
                token = auth_header[6:].strip()
            elif "x-mcp-api-key" in request.headers:
                token = request.headers.get("x-mcp-api-key", "").strip()

            if not token or token != expected_token:
                return JSONResponse(
                    {"error": "Unauthorized MCP Client. Valid Bearer token required."},
                    status_code=401,
                )

        return await call_next(request)


async def health_check(request):
    """Safe, public health check endpoint."""
    return JSONResponse(
        {
            "status": "ok",
            "service": "frappe-crm-mcp",
            "transport": "sse",
            "tools_count": 11,
            "tools": [
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
            ],
        }
    )


def create_app() -> Starlette:
    """Factory creating the ASGI Starlette app for remote SSE transport with CORS."""
    sec = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    app = mcp.sse_app(transport_security=sec)
    app.routes.insert(0, Route("/health", health_check, methods=["GET"]))
    app.add_middleware(MCPAuthMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app


# Module-level ASGI app for standard runners (e.g. uvicorn server:app)
app = create_app()


def main():
    parser = argparse.ArgumentParser(description="Frappe CRM MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol: 'stdio' (default) or 'sse'",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=config.mcp_port,
        help=f"Port for SSE transport (default: {config.mcp_port})",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=config.mcp_host,
        help=f"Host address for SSE transport (default: {config.mcp_host})",
    )

    args = parser.parse_args()

    if args.transport == "sse":
        import uvicorn
        print(f"[*] Starting Frappe CRM MCP Remote Server (SSE) on http://{args.host}:{args.port}...", file=sys.stderr)
        print(f"[*] Health check: http://{args.host}:{args.port}/health", file=sys.stderr)
        print(f"[*] SSE endpoint: http://{args.host}:{args.port}/sse", file=sys.stderr)
        if config.mcp_auth_token:
            print("[*] Security: Bearer token authentication ENABLED.", file=sys.stderr)
        else:
            print("[!] Security: MCP_AUTH_TOKEN not set; open access.", file=sys.stderr)
        uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
