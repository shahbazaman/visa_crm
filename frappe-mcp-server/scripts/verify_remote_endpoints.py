#!/usr/bin/env python3
"""
Safe Production Verification Script for Frappe CRM MCP Server on Render.
Probes public endpoints without logging or exposing secrets or customer PII.
Specifically detects Render edge routing states ('x-render-routing: no-server').
"""
import sys
import time
import urllib.request
import urllib.error
import json

DEFAULT_HOST = "https://visa-crm-mcp.onrender.com"

ENDPOINTS = [
    ("GET", "/", "Service Discovery Root"),
    ("GET", "/health", "Health Check"),
    ("OPTIONS", "/mcp", "CORS Preflight"),
    ("POST", "/mcp", "MCP Streamable HTTP Endpoint"),
    ("GET", "/.well-known/oauth-protected-resource/mcp", "OAuth Protected Resource Metadata"),
    ("GET", "/.well-known/oauth-authorization-server", "OAuth Authorization Server Metadata"),
    ("POST", "/token", "OAuth Token Endpoint"),
    ("POST", "/revoke", "OAuth Token Revocation Endpoint"),
]

def probe(base_url: str):
    print("=" * 80)
    print(f"PROBING PUBLIC MCP HOST: {base_url}")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print("=" * 80)

    has_no_server = False
    all_pass = True

    for method, path, desc in ENDPOINTS:
        url = base_url + path
        start = time.time()
        req = urllib.request.Request(
            url,
            method=method,
            headers={
                "User-Agent": "Antigravity-Production-Prober/1.0",
                "Origin": "https://gemini.google.com" if method == "OPTIONS" else "",
            },
        )
        if method == "POST":
            req.add_header("Content-Type", "application/json")
            data = b"{}"
        else:
            data = None

        try:
            with urllib.request.urlopen(req, data=data, timeout=8) as resp:
                elapsed = round((time.time() - start) * 1000, 2)
                server = resp.headers.get("server", "unknown")
                routing = resp.headers.get("x-render-routing", "active")
                print(f"[{method:<7}] {path:<45} -> HTTP {resp.status} ({elapsed}ms) [server: {server}]")
        except urllib.error.HTTPError as e:
            elapsed = round((time.time() - start) * 1000, 2)
            server = e.headers.get("server", "unknown")
            routing = e.headers.get("x-render-routing", "none")
            
            if routing == "no-server":
                has_no_server = True
                all_pass = False
                print(f"[{method:<7}] {path:<45} -> HTTP {e.code} ({elapsed}ms) [FAIL: x-render-routing: no-server]")
            elif path == "/mcp" and e.code == 401:
                # 401 Unauthorized with WWW-Authenticate challenge is expected on unauthenticated /mcp probe
                www_auth = e.headers.get("www-authenticate", "")
                if "Bearer" in www_auth and "resource_metadata=" in www_auth:
                    print(f"[{method:<7}] {path:<45} -> HTTP 401 ({elapsed}ms) [PASS: RFC 9728 Bearer challenge present]")
                else:
                    print(f"[{method:<7}] {path:<45} -> HTTP 401 ({elapsed}ms) [WARN: Missing resource_metadata]")
            elif path in ("/token", "/revoke") and e.code in (400, 401):
                print(f"[{method:<7}] {path:<45} -> HTTP {e.code} ({elapsed}ms) [PASS: Properly rejected empty credentials]")
            else:
                print(f"[{method:<7}] {path:<45} -> HTTP {e.code} ({elapsed}ms) [server: {server}, routing: {routing}]")
                all_pass = False
        except Exception as err:
            elapsed = round((time.time() - start) * 1000, 2)
            print(f"[{method:<7}] {path:<45} -> NETWORK ERROR ({elapsed}ms): {err}")
            all_pass = False

    print("=" * 80)
    if has_no_server:
        print("RESULT: FAIL — Render edge router reports 'x-render-routing: no-server'.")
        print("CAUSE:  The Render Web Service has not been provisioned on dashboard.render.com.")
        return 1
    elif not all_pass:
        print("RESULT: FAIL — One or more mandatory public endpoints failed.")
        return 1
    else:
        print("RESULT: PASS — All public endpoints are healthy, responsive, and OAuth-compliant.")
        return 0

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HOST
    sys.exit(probe(target))
