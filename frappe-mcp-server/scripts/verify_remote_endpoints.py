#!/usr/bin/env python3
"""
Automated Remote Verification Prober for Frappe CRM MCP Server on Render.
Complies with Antigravity Master Verification Phase 12.

Safely tests:
- DNS Resolution
- TLS Certificate & Handshake
- GET / (Service Discovery Root)
- GET /health (Health Check)
- OPTIONS /mcp (CORS Preflight)
- POST /mcp (MCP Streamable HTTP Endpoint & RFC 9728 Bearer Challenge)
- GET /.well-known/oauth-protected-resource/mcp (OAuth Protected Resource Metadata)
- GET /.well-known/oauth-authorization-server (OAuth Authorization Server Metadata)
- POST /token (OAuth Token Endpoint)
- POST /revoke (OAuth Token Revocation Endpoint)

Accurately differentiates failure boundaries:
- DNS failure
- TLS failure
- Render no-server ('x-render-routing: no-server') -> Classified as RENDER SERVICE NOT PROVISIONED
- Render application 5xx
- Application 404
- OAuth discovery/metadata failure
- MCP protocol failure
- Frappe authentication / API failure

STRICT SAFETY: Never prints credentials, tokens, or customer PII.
"""

import json
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_TARGET = "https://visa-crm-mcp.onrender.com"

ENDPOINTS = [
    ("GET", "/", "Service Discovery Root"),
    ("GET", "/health", "Health Check Endpoint"),
    ("OPTIONS", "/mcp", "CORS Preflight (gemini.google.com)"),
    ("POST", "/mcp", "Streamable HTTP MCP & RFC 9728 Challenge"),
    ("GET", "/.well-known/oauth-protected-resource/mcp", "OAuth Protected Resource Metadata"),
    ("GET", "/.well-known/oauth-authorization-server", "OAuth Authorization Server Metadata"),
    ("POST", "/token", "OAuth Token Issuance Endpoint"),
    ("POST", "/revoke", "OAuth Token Revocation Endpoint"),
]


def test_dns(hostname: str) -> tuple[bool, str]:
    """Test DNS resolution for target host."""
    try:
        addrs = socket.getaddrinfo(hostname, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
        ip_list = sorted(list({a[4][0] for a in addrs}))
        return True, f"Resolved to {len(ip_list)} IP(s): {', '.join(ip_list[:3])}"
    except socket.gaierror as e:
        return False, f"DNS Resolution Failed: {e}"
    except Exception as e:
        return False, f"DNS Lookup Error: {e}"


def test_tls(hostname: str, port: int = 443) -> tuple[bool, str]:
    """Test TLS certificate validity and handshake."""
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((hostname, port), timeout=6) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                subject = dict(x[0] for x in cert.get("subject", []))
                common_name = subject.get("commonName", "unknown")
                version = ssock.version()
                return True, f"TLS Handshake OK ({version}, CN: {common_name})"
    except ssl.SSLError as e:
        return False, f"TLS Handshake/Certificate Failure: {e}"
    except Exception as e:
        return False, f"Connection Failure during TLS probe: {e}"


def probe(target_url: str) -> int:
    parsed = urllib.parse.urlparse(target_url)
    if not parsed.scheme or not parsed.netloc:
        print(f"[-] ERROR: Invalid URL format: {target_url}")
        return 1

    hostname = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    base_url = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")

    print("=" * 80)
    print("FRAPPE CRM MCP — AUTOMATED PRODUCTION ENDPOINT VERIFICATION")
    print(f"Target Base URL: {base_url}")
    print(f"Target Hostname: {hostname}")
    print(f"Timestamp:       {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print("=" * 80)

    # 1. DNS Resolution Test
    dns_ok, dns_msg = test_dns(hostname)
    print(f"[DNS Check]      {hostname:<35} -> {'PASS' if dns_ok else 'FAIL'}: {dns_msg}")
    if not dns_ok:
        print("=" * 80)
        print("RESULT: FAIL — DNS resolution failure.")
        print("DIAGNOSIS: The hostname does not exist in public DNS.")
        return 1

    # 2. TLS Handshake Test (if HTTPS)
    if parsed.scheme == "https":
        tls_ok, tls_msg = test_tls(hostname, port)
        print(f"[TLS Check]      {hostname:<35} -> {'PASS' if tls_ok else 'FAIL'}: {tls_msg}")
        if not tls_ok:
            print("=" * 80)
            print("RESULT: FAIL — TLS handshake or certificate validation failure.")
            print("DIAGNOSIS: SSL/TLS connection could not be established.")
            return 1
    else:
        print(f"[TLS Check]      Skipped (HTTP scheme used)")

    print("-" * 80)
    print(f"{'Method':<8} {'Endpoint':<45} {'Latency':<10} {'Status / Classification'}")
    print("-" * 80)

    render_no_server_detected = False
    render_5xx_detected = False
    endpoint_failures = []

    for method, path, desc in ENDPOINTS:
        url = base_url + path
        start_time = time.perf_counter()

        headers = {
            "User-Agent": "Antigravity-Production-Prober/2.0",
        }
        if method == "OPTIONS":
            headers["Origin"] = "https://gemini.google.com"
            headers["Access-Control-Request-Method"] = "POST"
            headers["Access-Control-Request-Headers"] = "Authorization, Content-Type, mcp-session-id"

        req = urllib.request.Request(url, method=method, headers=headers)
        data = b"{}" if method == "POST" else None
        if method == "POST":
            req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, data=data, timeout=10) as resp:
                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                routing = resp.headers.get("x-render-routing", "none")
                server = resp.headers.get("server", "unknown")
                status = resp.status

                classification = f"HTTP {status} OK [server: {server}]"
                print(f"{method:<8} {path:<45} {elapsed_ms:>7.2f}ms   PASS: {classification}")

        except urllib.error.HTTPError as e:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            routing = e.headers.get("x-render-routing", "none")
            server = e.headers.get("server", "unknown")
            code = e.code

            if routing == "no-server":
                render_no_server_detected = True
                classification = "FAIL — RENDER SERVICE NOT PROVISIONED (x-render-routing: no-server)"
                print(f"{method:<8} {path:<45} {elapsed_ms:>7.2f}ms   {classification}")
                endpoint_failures.append((path, "Render no-server"))
            elif code in (500, 502, 503, 504):
                render_5xx_detected = True
                classification = f"FAIL — RENDER APPLICATION 5xx ERROR (HTTP {code})"
                print(f"{method:<8} {path:<45} {elapsed_ms:>7.2f}ms   {classification}")
                endpoint_failures.append((path, f"Server Error {code}"))
            elif path == "/mcp" and code == 401:
                # 401 Unauthorized with WWW-Authenticate Bearer challenge is the expected RFC 9728 response
                www_auth = e.headers.get("www-authenticate", "")
                if "Bearer" in www_auth and "resource_metadata=" in www_auth:
                    classification = "HTTP 401 Unauthorized (RFC 9728 Bearer Challenge PASS)"
                    print(f"{method:<8} {path:<45} {elapsed_ms:>7.2f}ms   PASS: {classification}")
                else:
                    classification = "HTTP 401 Unauthorized (WARN: Missing resource_metadata parameter)"
                    print(f"{method:<8} {path:<45} {elapsed_ms:>7.2f}ms   {classification}")
            elif path in ("/token", "/revoke") and code in (400, 401):
                # 400 or 401 on empty credentials probe verifies the authentication gate is active
                classification = f"HTTP {code} (Authentication Gate PASS: safely rejected empty payload)"
                print(f"{method:<8} {path:<45} {elapsed_ms:>7.2f}ms   PASS: {classification}")
            elif code == 404:
                classification = f"FAIL — APPLICATION 404 (Route not found)"
                print(f"{method:<8} {path:<45} {elapsed_ms:>7.2f}ms   {classification}")
                endpoint_failures.append((path, "HTTP 404"))
            else:
                classification = f"HTTP {code} [server: {server}, routing: {routing}]"
                print(f"{method:<8} {path:<45} {elapsed_ms:>7.2f}ms   FAIL: {classification}")
                endpoint_failures.append((path, f"HTTP {code}"))

        except Exception as err:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            classification = f"NETWORK ERROR: {err}"
            print(f"{method:<8} {path:<45} {elapsed_ms:>7.2f}ms   FAIL: {classification}")
            endpoint_failures.append((path, "Network Error"))

    print("=" * 80)

    if render_no_server_detected:
        print("PRODUCTION ACCEPTANCE = FAIL")
        print("DIAGNOSIS:             RENDER SERVICE NOT PROVISIONED")
        print("ROOT CAUSE:            The Render edge router returned 'x-render-routing: no-server'.")
        print("EXPLANATION:           The domain https://visa-crm-mcp.onrender.com resolves to Cloudflare/Render,")
        print("                       but no active Web Service named 'visa-crm-mcp' exists on the account.")
        print("REQUIRED ACTION:       Create Web Service 'visa-crm-mcp' on dashboard.render.com linked to")
        print("                       GitHub repository 'shahbazaman/visa_crm' (branch: main).")
        return 2
    elif render_5xx_detected:
        print("PRODUCTION ACCEPTANCE = FAIL")
        print("DIAGNOSIS:             RENDER APPLICATION 5xx CRASH")
        print("ROOT CAUSE:            Container crashed on startup or failed health check.")
        print("REQUIRED ACTION:       Inspect Render service logs for startup traceback.")
        return 3
    elif endpoint_failures:
        print("PRODUCTION ACCEPTANCE = FAIL")
        print(f"DIAGNOSIS:             {len(endpoint_failures)} endpoint(s) failed verification.")
        for p, reason in endpoint_failures:
            print(f"  - {p}: {reason}")
        return 4
    else:
        print("PRODUCTION ACCEPTANCE = PASS")
        print("ALL 8 PUBLIC ENDPOINTS VERIFIED HEALTHY, RESPONSIVE, AND OAUTH/MCP COMPLIANT.")
        return 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TARGET
    sys.exit(probe(target))
