"""
Frappe CRM Model Context Protocol (MCP) Server.
Connects Google Gemini to production Frappe CRM via controlled Phase 1 API.
Supports both local Stdio transport and remote SSE transport with Bearer token authentication.
"""

import argparse
import sys
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.middleware.base import BaseHTTPMiddleware
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from config import config
from tools.leads import get_today_leads as fetch_today_leads


# Initialize MCPServer instance
mcp = MCPServer(
    name="frappe-crm",
    instructions=(
        "You are an assistant connected to the Visa CRM Frappe production system. "
        "Use the get_today_leads tool to query real-time CRM lead records for today. "
        "Always present accurate data and do not fabricate information."
    ),
)


@mcp.tool(
    name="get_today_leads",
    description="Returns today's CRM Lead records from the production Visa CRM Frappe instance. This is a read-only reporting tool.",
)
async def get_today_leads() -> dict:
    """
    Returns today's CRM Lead records from the production Visa CRM Frappe instance. This is a read-only reporting tool.
    """
    return await fetch_today_leads()


class MCPAuthMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware for remote incoming MCP requests.
    Validates Authorization Bearer token against MCP_AUTH_TOKEN when configured.
    Health check (/health) is always public.
    """

    async def dispatch(self, request, call_next):
        # Allow health checks without authentication
        if request.url.path in ("/health", "/health/"):
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
            "tools": ["get_today_leads"],
        }
    )


def create_app() -> Starlette:
    """Factory creating the ASGI Starlette app for remote SSE transport."""
    sec = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    app = mcp.sse_app(transport_security=sec)
    app.routes.insert(0, Route("/health", health_check, methods=["GET"]))
    app.add_middleware(MCPAuthMiddleware)
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
