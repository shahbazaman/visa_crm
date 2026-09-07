"""
Frappe CRM Model Context Protocol (MCP) Server.
Connects Google Gemini Spark to production Frappe CRM via controlled read-only reporting APIs.
Supports:
- Modern Streamable HTTP transport (/mcp) with RFC 9728 & RFC 8414 OAuth 2.0 discovery & token issuance.
- Local Stdio transport for desktop/CLI agents.
- Legacy SSE transport for backward compatibility.
- 11 strictly read-only business reporting tools with MCP annotations and strict date validation.
"""

import argparse
import sys
from typing import Optional
from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.middleware.cors import CORSMiddleware
from mcp.server.mcpserver import MCPServer
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
# Enable wildcard matching (fnmatch) for TransportSecurityMiddleware to support Cloudflare tunnels
import fnmatch
from mcp.server.transport_security import TransportSecurityMiddleware

def _patched_validate_host(self, host: str | None) -> bool:
    if not host:
        return False
    for pattern in self.settings.allowed_hosts:
        if pattern.endswith(":*"):
            base_pattern = pattern[:-2]
            if ":" in host:
                h_name, _ = host.split(":", 1)
                if fnmatch.fnmatch(h_name, base_pattern) or fnmatch.fnmatch(host, pattern):
                    return True
            elif fnmatch.fnmatch(host, base_pattern):
                return True
        elif fnmatch.fnmatch(host, pattern):
            return True
    return False

def _patched_validate_origin(self, origin: str | None) -> bool:
    if not origin:
        return True
    for pattern in self.settings.allowed_origins:
        if pattern.endswith(":*"):
            base_pattern = pattern[:-2]
            if ":" in origin:
                o_name = origin.rsplit(":", 1)[0]
                if fnmatch.fnmatch(o_name, base_pattern) or fnmatch.fnmatch(origin, pattern):
                    return True
            elif fnmatch.fnmatch(origin, base_pattern):
                return True
        elif fnmatch.fnmatch(origin, pattern):
            return True
    return False

TransportSecurityMiddleware._validate_host = _patched_validate_host
TransportSecurityMiddleware._validate_origin = _patched_validate_origin

# =============================================================================
# DYNAMIC OAUTH / WWW-AUTHENTICATE PATCH FOR STREAMABLE HTTP
# Ensures WWW-Authenticate challenge header always contains the public HTTPS
# metadata URL from the incoming request headers (or config.mcp_public_url).
# =============================================================================
from mcp.server.auth.middleware.bearer_auth import RequireAuthMiddleware
import json
import logging
import time
import uuid

_orig_send_auth_error = RequireAuthMiddleware._send_auth_error

async def _dynamic_send_auth_error(self, send, status_code: int, error: str, description: str) -> None:
    req_metadata_url = getattr(self, "_current_resource_metadata_url", None) or self.resource_metadata_url
    www_auth_parts = [f'error="{error}"', f'error_description="{description}"']
    if req_metadata_url:
        www_auth_parts.append(f'resource_metadata="{req_metadata_url}"')

    www_authenticate = f"Bearer {', '.join(www_auth_parts)}"
    body = {"error": error, "error_description": description}
    body_bytes = json.dumps(body).encode()

    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body_bytes)).encode()),
                (b"www-authenticate", www_authenticate.encode()),
                (b"access-control-allow-origin", b"*"),
                (b"access-control-expose-headers", b"www-authenticate, mcp-session-id"),
            ],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": body_bytes,
        }
    )

_orig_require_auth_call = RequireAuthMiddleware.__call__

async def _dynamic_require_auth_call(self, scope, receive, send) -> None:
    if scope.get("type") == "http":
        headers = dict(scope.get("headers", []))
        xf_proto = headers.get(b"x-forwarded-proto", b"").decode("latin1")
        xf_host = headers.get(b"x-forwarded-host", b"").decode("latin1")
        host_hdr = headers.get(b"host", b"").decode("latin1")

        configured = config.mcp_public_url
        if configured and not configured.startswith("http://127.0.0.1") and not configured.startswith("http://localhost"):
            base_url = configured
        elif xf_host or host_hdr:
            scheme = xf_proto or scope.get("scheme", "http")
            netloc = xf_host or host_hdr
            base_url = f"{scheme}://{netloc}".rstrip("/")
        else:
            base_url = configured or "http://127.0.0.1:8000"

        self._current_resource_metadata_url = f"{base_url}/.well-known/oauth-protected-resource/mcp"
    await _orig_require_auth_call(self, scope, receive, send)

RequireAuthMiddleware._send_auth_error = _dynamic_send_auth_error
RequireAuthMiddleware.__call__ = _dynamic_require_auth_call


# Safe Structured Access Logging
logger = logging.getLogger("frappe_mcp.access")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

class SafeAccessLoggingMiddleware:
    """Logs incoming HTTP requests safely without logging tokens, keys, or customer data."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        req_id = uuid.uuid4().hex[:8]
        method = scope.get("method", "GET")
        path = scope.get("path", "/")
        start_time = time.time()
        status_code = [200]

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_code[0] = message.get("status", 200)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            logger.info(f"[{req_id}] {method} {path} -> {status_code[0]} ({duration_ms}ms)")

import mcp.types as types

from config import config
from auth import (
    get_base_url,
    frappe_token_verifier,
    get_oauth_protected_resource,
    get_oauth_authorization_server,
    register_endpoint,
    authorize_endpoint,
    token_endpoint,
    revoke_endpoint,
)
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

# Standard read-only tool annotations for all reporting tools
READ_ONLY_ANNOTATIONS = types.ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)

# Configure OAuth AuthSettings for MCP server
mcp_auth_settings = AuthSettings(
    issuer_url=AnyHttpUrl(config.mcp_public_url),
    resource_server_url=AnyHttpUrl(f"{config.mcp_public_url}/mcp"),
    required_scopes=["mcp:read"],
)

# Initialize MCPServer instance with authentication & verifier
mcp = MCPServer(
    name="frappe-crm",
    instructions=(
        "You are an assistant connected to the Visa CRM Frappe production system. "
        "Use the provided read-only reporting tools to query real-time CRM leads, departments, "
        "counselors, sources, reports, follow-ups, tasks, visa applications, and management briefings. "
        "Always present accurate live data and do not fabricate information. "
        "Interprets natural-language date questions into explicit YYYY-MM-DD format using Frappe server timezone."
    ),
    auth=mcp_auth_settings,
    token_verifier=frappe_token_verifier,
)


# =============================================================================
# 1. LEAD TOOLS
# =============================================================================

@mcp.tool(
    name="get_today_leads",
    description=(
        "Returns CRM Lead records created today in the production Frappe CRM. "
        "Use this tool when the user asks: "
        "- today's leads "
        "- leads received today "
        "- how many leads came today "
        "- today's lead report "
        "- new leads today"
    ),
    annotations=READ_ONLY_ANNOTATIONS,
)
async def get_today_leads() -> dict:
    """Returns today's CRM Lead records from the production Visa CRM Frappe instance."""
    return await fetch_today_leads()


@mcp.tool(
    name="get_leads_by_date",
    description=(
        "Returns CRM leads created on a specific calendar date (date in YYYY-MM-DD format). "
        "Use this tool when the user asks for leads on a specific day, such as: "
        "- yesterday's leads "
        "- leads on 2026-09-06 "
        "- leads from last Friday "
        "- leads on a particular date"
    ),
    annotations=READ_ONLY_ANNOTATIONS,
)
async def get_leads_by_date(date: str) -> dict:
    """Returns CRM leads created on a specific date (YYYY-MM-DD)."""
    return await fetch_leads_by_date(date)


@mcp.tool(
    name="get_lead_report",
    description=(
        "Returns an aggregated CRM lead report for a date range (start_date and end_date in YYYY-MM-DD format). "
        "Includes total leads, breakdown by department, breakdown by source, breakdown by status, "
        "and assigned vs unassigned distribution. Use when the user asks: "
        "- this week's leads / weekly lead report "
        "- this month's leads / monthly sales report "
        "- lead statistics between start_date and end_date "
        "- lead pipeline overview across a date range"
    ),
    annotations=READ_ONLY_ANNOTATIONS,
)
async def get_lead_report(start_date: str, end_date: str) -> dict:
    """Returns an aggregated CRM lead report for a date range."""
    return await fetch_lead_report(start_date, end_date)


@mcp.tool(
    name="get_leads_by_department",
    description=(
        "Returns CRM leads belonging to a specific department in Frappe CRM. "
        "Production departments include 'Holidays - MEH' and 'Global visa - MEH'. "
        "Use when the user asks: "
        "- show leads for Holidays "
        "- leads in Global visa department "
        "- which leads belong to Holidays department"
    ),
    annotations=READ_ONLY_ANNOTATIONS,
)
async def get_leads_by_department(department: str) -> dict:
    """Returns CRM leads belonging to a specific department."""
    return await fetch_leads_by_department(department)


@mcp.tool(
    name="get_leads_by_counselor",
    description=(
        "Returns CRM leads assigned to a specific counselor or user identifier (e.g. 'Administrator', counselor email). "
        "Use when the user asks: "
        "- leads assigned to [counselor name] "
        "- show counselor's leads "
        "- who is working on which leads"
    ),
    annotations=READ_ONLY_ANNOTATIONS,
)
async def get_leads_by_counselor(counselor: str) -> dict:
    """Returns CRM leads assigned to a specific counselor."""
    return await fetch_leads_by_counselor(counselor)


@mcp.tool(
    name="get_lead_sources",
    description=(
        "Returns lead acquisition counts aggregated by source channel (e.g. Meta Instant Form, WhatsApp, Website) "
        "for an optional date range (YYYY-MM-DD). "
        "Use when the user asks: "
        "- where are our leads coming from? "
        "- lead breakdown by source / marketing channels "
        "- how many leads came from Meta vs WhatsApp?"
    ),
    annotations=READ_ONLY_ANNOTATIONS,
)
async def get_lead_sources(
    start_date: Optional[str] = None, end_date: Optional[str] = None
) -> dict:
    """Returns lead acquisition counts aggregated by source channel."""
    return await fetch_lead_sources(start_date, end_date)


@mcp.tool(
    name="get_unassigned_leads",
    description=(
        "Returns CRM leads where counselor/owner assignment is currently missing or pending, "
        "for an optional date range (YYYY-MM-DD). "
        "Use when the user asks: "
        "- show unassigned leads "
        "- leads without a counselor "
        "- unallocated leads backlog"
    ),
    annotations=READ_ONLY_ANNOTATIONS,
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
    description=(
        "Returns controlled follow-up and reminder records linked to CRM leads for an optional date range (YYYY-MM-DD). "
        "Use when the user asks: "
        "- today's follow-ups "
        "- follow-up calls scheduled for today/this week "
        "- pending reminders for leads"
    ),
    annotations=READ_ONLY_ANNOTATIONS,
)
async def get_followups(
    start_date: Optional[str] = None, end_date: Optional[str] = None
) -> dict:
    """Returns controlled follow-up and reminder records linked to CRM leads."""
    return await fetch_followups(start_date, end_date)


@mcp.tool(
    name="get_tasks",
    description=(
        "Returns controlled task records linked to CRM leads or employees, with optional date range (YYYY-MM-DD) "
        "and optional assigned_employee filter. "
        "Use when the user asks: "
        "- pending tasks for today "
        "- tasks assigned to employee "
        "- what tasks are due?"
    ),
    annotations=READ_ONLY_ANNOTATIONS,
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
    description=(
        "Returns controlled Visa Application reporting data, with optional date range (YYYY-MM-DD) "
        "and optional status filter (e.g. 'Draft', 'Submitted', 'Approved', 'Rejected'). "
        "Use when the user asks: "
        "- visa applications created today / this month "
        "- how many visa applications were approved? "
        "- status of recent visa applications"
    ),
    annotations=READ_ONLY_ANNOTATIONS,
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
        "and items requiring managerial attention. "
        "Use when the user asks: "
        "- give me a management summary for today "
        "- executive briefing / daily summary "
        "- what needs attention today? "
        "- high-level CRM status report"
    ),
    annotations=READ_ONLY_ANNOTATIONS,
)
async def get_management_summary(date: Optional[str] = None) -> dict:
    """Returns a comprehensive executive management briefing."""
    return await fetch_management_summary(date)


# =============================================================================
# 4. CUSTOM HTTP ROUTES (HEALTH, OAUTH & DISCOVERY)


@mcp.custom_route("/", methods=["GET", "HEAD", "OPTIONS"])
async def route_root(request) -> Response:
    """Root discovery endpoint for Gemini Spark connected app setup."""
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            },
        )
    base_url = get_base_url(request)
    return JSONResponse(
        {
            "service": "frappe-crm-mcp",
            "status": "ok",
            "version": "1.0.0",
            "description": "Production Frappe CRM MCP Server for Google Gemini Spark",
            "transport": "streamable-http",
            "endpoints": {
                "mcp": f"{base_url}/mcp",
                "health": f"{base_url}/health",
                "authorization_server": f"{base_url}/.well-known/oauth-authorization-server",
                "protected_resource": f"{base_url}/.well-known/oauth-protected-resource",
                "token": f"{base_url}/token",
                "authorize": f"{base_url}/authorize",
            },
            "tools_count": 11,
        },
        headers={
            "Access-Control-Allow-Origin": "*",
            "Link": f'<{base_url}/.well-known/oauth-protected-resource/mcp>; rel="resource-metadata"',
        },
    )
# =============================================================================

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request) -> JSONResponse:
    """Safe, public health check endpoint."""
    base_url = get_base_url(request)
    return JSONResponse(
        {
            "status": "ok",
            "service": "frappe-crm-mcp",
            "transport": "streamable-http",
            "tools_count": 11,
            "oauth": {
                "discovery": f"{base_url}/.well-known/oauth-authorization-server",
                "protected_resource": f"{base_url}/.well-known/oauth-protected-resource",
            },
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
        },
        headers={"Access-Control-Allow-Origin": "*"},
    )


# OAuth Discovery & Protected Resource Metadata Endpoints
@mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET", "OPTIONS"])
@mcp.custom_route("/.well-known/oauth-protected-resource/mcp", methods=["GET", "OPTIONS"])
async def route_oauth_protected_resource(request):
    return await get_oauth_protected_resource(request)


@mcp.custom_route("/.well-known/oauth-authorization-server", methods=["GET", "OPTIONS"])
@mcp.custom_route("/.well-known/openid-configuration", methods=["GET", "OPTIONS"])
async def route_oauth_authorization_server(request):
    return await get_oauth_authorization_server(request)


# OAuth Lifecycle Endpoints
@mcp.custom_route("/register", methods=["POST", "OPTIONS"])
async def route_register(request):
    return await register_endpoint(request)


@mcp.custom_route("/authorize", methods=["GET", "POST"])
async def route_authorize(request):
    return await authorize_endpoint(request)


@mcp.custom_route("/token", methods=["POST", "OPTIONS"])
async def route_token(request):
    return await token_endpoint(request)


@mcp.custom_route("/revoke", methods=["POST", "OPTIONS"])
async def route_revoke(request):
    return await revoke_endpoint(request)


# Legacy SSE Compatibility Route
@mcp.custom_route("/sse", methods=["GET", "OPTIONS"])
async def route_legacy_sse(request):
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Authorization, Content-Type",
            },
        )
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    auth_user = await frappe_token_verifier.verify_token(token)
    if not auth_user:
        return JSONResponse(
            {"error": "Unauthorized MCP Client. Valid Bearer token required."},
            status_code=401,
            headers={"WWW-Authenticate": f'Bearer resource_metadata="{config.mcp_public_url}/.well-known/oauth-protected-resource"'},
        )
    return JSONResponse(
        {"status": "ok", "message": "Legacy SSE endpoint. Streamable HTTP active at /mcp"},
        status_code=200,
    )


# =============================================================================
# 5. APP FACTORY
# =============================================================================

def create_app() -> Starlette:
    """Factory creating the ASGI Starlette app for modern Streamable HTTP transport with CORS."""
    sec = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=config.allowed_hosts,
        allowed_origins=config.allowed_origins,
    )

    app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        transport_security=sec,
        host=config.mcp_host,
    )

    # Outermost CORS middleware to ensure browser/Gemini requests pass cleanly
    app.add_middleware(SafeAccessLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS", "HEAD"],
        allow_headers=["*"],
        expose_headers=["mcp-session-id", "mcp-protocol-version", "www-authenticate"],
    )
    return app


# Module-level ASGI app for standard runners (e.g. uvicorn server:app)
app = create_app()


def main():
    parser = argparse.ArgumentParser(description="Frappe CRM MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "streamable-http", "sse"],
        default="stdio",
        help="Transport protocol: 'http' / 'streamable-http' (Streamable HTTP, default for web/Gemini), 'sse', or 'stdio'",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=config.mcp_port,
        help=f"Port for HTTP transport (default: {config.mcp_port})",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=config.mcp_host,
        help=f"Host address for HTTP transport (default: {config.mcp_host})",
    )

    args = parser.parse_args()

    if args.transport in ("http", "streamable-http"):
        import uvicorn
        base = config.mcp_public_url
        print(f"[*] Starting Frappe CRM MCP Server (Streamable HTTP) on http://{args.host}:{args.port}...", file=sys.stderr)
        print(f"[*] MCP Endpoint:      {base}/mcp", file=sys.stderr)
        print(f"[*] Health Check:      {base}/health", file=sys.stderr)
        print(f"[*] OAuth Discovery:   {base}/.well-known/oauth-authorization-server", file=sys.stderr)
        print(f"[*] Resource Metadata: {base}/.well-known/oauth-protected-resource", file=sys.stderr)
        print(f"[*] Gemini Client ID:  {config.gemini_client_id}", file=sys.stderr)
        print(f"[*] Security: DNS Rebinding Protection ENABLED, OAuth 2.0 JWT Token Validation ENABLED.", file=sys.stderr)
        uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")
    elif args.transport == "sse":
        import uvicorn
        print(f"[*] Starting Frappe CRM MCP Server (Legacy SSE) on http://{args.host}:{args.port}...", file=sys.stderr)
        sec = TransportSecuritySettings(enable_dns_rebinding_protection=False)
        sse_app = mcp.sse_app(transport_security=sec)
        uvicorn.run(sse_app, host=args.host, port=args.port, log_level="info")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
