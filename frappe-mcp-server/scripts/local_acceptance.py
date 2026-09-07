#!/usr/bin/env python3
"""
Deterministic Local Production Acceptance Test for Frappe CRM MCP Server.
Complies with Antigravity Master Verification Phase 16.

Features:
1. Starts the server on a dynamic, OS-assigned random port.
2. Sets PORT, MCP_HOST, and MCP_PUBLIC_URL dynamically.
3. Validates full HTTP, OAuth 2.0, and Streamable HTTP MCP protocols.
4. Validates real live Frappe Cloud tool execution.
5. Tests token revocation and session lifecycle.
6. Terminates server cleanly and verifies zero lingering processes/ports.
7. Completely independent of fixed ports (no 8000, no 8080 assumptions).
"""

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)


def get_free_port() -> int:
    """Find a guaranteed free dynamic port assigned by OS."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def is_port_in_use(port: int) -> bool:
    """Check if a port is in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def make_request(
    url: str,
    method: str = "GET",
    headers: dict = None,
    data: dict = None,
    timeout: float = 10.0,
) -> tuple[int, dict, dict]:
    """Execute HTTP request and return (status_code, headers, response_data). Handles both JSON & SSE streams."""
    headers = dict(headers or {})
    encoded_data = None
    if data is not None:
        encoded_data = json.dumps(data).encode("utf-8")
        if "Content-Type" not in headers and "content-type" not in headers:
            headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=encoded_data, method=method)
    for k, v in headers.items():
        req.add_header(k, v)

    def parse_body(resp_body: str) -> dict:
        # Check if SSE stream
        if "data: " in resp_body:
            for line in resp_body.splitlines():
                if line.strip().startswith("data: "):
                    raw_data = line.strip()[6:].strip()
                    try:
                        return json.loads(raw_data)
                    except Exception:
                        pass
        try:
            return json.loads(resp_body)
        except Exception:
            return {"raw": resp_body}

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_body = resp.read().decode("utf-8")
            resp_headers = dict(resp.headers)
            parsed_json = parse_body(resp_body)
            return resp.status, resp_headers, parsed_json
    except urllib.error.HTTPError as e:
        resp_body = e.read().decode("utf-8")
        resp_headers = dict(e.headers)
        parsed_json = parse_body(resp_body)
        return e.code, resp_headers, parsed_json


def run_local_acceptance():
    print("=" * 80)
    print("DETERMINISTIC LOCAL ACCEPTANCE TEST — FRAPPE CRM MCP SERVER")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print("=" * 80)

    # 1. Allocate dynamic ephemeral port
    port = get_free_port()
    base_url = f"http://127.0.0.1:{port}"
    print(f"[*] Step 1: Allocated Dynamic Ephemeral Port: {port}")
    print(f"[*] Base URL: {base_url}")

    # Set up environment variables
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["MCP_HOST"] = "127.0.0.1"
    env["MCP_PUBLIC_URL"] = base_url

    # 2. Launch server process
    print(f"[*] Step 2: Launching server process on port {port}...")
    server_proc = subprocess.Popen(
        [sys.executable, "server.py", "--transport", "http", "--host", "127.0.0.1", "--port", str(port)],
        cwd=server_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        # 3. Poll for readiness
        print("[*] Step 3: Waiting for server readiness...")
        start_wait = time.time()
        ready = False
        while time.time() - start_wait < 8.0:
            if server_proc.poll() is not None:
                _, err = server_proc.communicate()
                raise RuntimeError(f"Server exited prematurely with code {server_proc.returncode}: {err.decode()}")
            try:
                code, _, data = make_request(f"{base_url}/health", timeout=1.0)
                if code == 200 and data.get("status") == "ok":
                    ready = True
                    break
            except Exception:
                time.sleep(0.2)

        if not ready:
            raise RuntimeError("Server failed to become ready within 8 seconds.")
        print(f"[+] Server ready in {round((time.time() - start_wait) * 1000, 2)}ms")

        # 4. Test Root Discovery
        print("[*] Step 4: Testing GET / (Service Discovery)...")
        code, _, data = make_request(f"{base_url}/")
        assert code == 200, f"Expected 200, got {code}"
        assert data.get("service") == "frappe-crm-mcp", f"Unexpected service name: {data.get('service')}"
        assert data.get("tools_count") == 11, f"Expected 11 tools, got {data.get('tools_count')}"
        assert data.get("endpoints", {}).get("mcp") == f"{base_url}/mcp"
        print("[+] Root Discovery: PASS")

        # 5. Test Health Endpoint
        print("[*] Step 5: Testing GET /health...")
        code, _, data = make_request(f"{base_url}/health")
        assert code == 200, f"Expected 200, got {code}"
        assert data.get("status") == "ok"
        assert len(data.get("tools", [])) == 11
        print("[+] Health Check: PASS (11 tools advertised)")

        # 6. Test OAuth Metadata
        print("[*] Step 6: Testing RFC 9728 & RFC 8414 OAuth Metadata...")
        code, _, res_meta = make_request(f"{base_url}/.well-known/oauth-protected-resource/mcp")
        assert code == 200, f"Expected 200, got {code}"
        assert res_meta.get("resource") == f"{base_url}/mcp"

        code, _, auth_meta = make_request(f"{base_url}/.well-known/oauth-authorization-server")
        assert code == 200, f"Expected 200, got {code}"
        assert auth_meta.get("token_endpoint") == f"{base_url}/token"
        print("[+] OAuth Metadata: PASS")

        # 7. Test CORS Preflight
        print("[*] Step 7: Testing CORS Preflight for Gemini...")
        code, headers, _ = make_request(
            f"{base_url}/mcp",
            method="OPTIONS",
            headers={
                "Origin": "https://gemini.google.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization, Content-Type, mcp-session-id",
            },
        )
        assert code == 200, f"Expected 200, got {code}"
        allow_origin = headers.get("access-control-allow-origin") or headers.get("Access-Control-Allow-Origin")
        assert allow_origin in ("https://gemini.google.com", "*"), f"Unexpected allow-origin: {allow_origin}"
        print("[+] CORS Preflight: PASS")

        # 8. Test Unauthenticated MCP Challenge
        print("[*] Step 8: Testing Unauthenticated POST /mcp RFC 9728 Bearer challenge...")
        code, headers, _ = make_request(f"{base_url}/mcp", method="POST", data={})
        assert code == 401, f"Expected 401, got {code}"
        www_auth = headers.get("www-authenticate") or headers.get("WWW-Authenticate", "")
        assert "Bearer" in www_auth and "resource_metadata=" in www_auth
        print("[+] RFC 9728 Challenge: PASS")

        # 9. Test OAuth Token Acquisition
        print("[*] Step 9: Testing OAuth Token Issuance...")
        # Test invalid credentials
        code, _, _ = make_request(
            f"{base_url}/token",
            method="POST",
            data={"grant_type": "client_credentials", "client_id": "gemini-spark-client", "client_secret": "wrong"},
        )
        assert code == 401, f"Expected 401 for wrong secret, got {code}"

        # Test valid credentials
        from config import config
        client_id = config.gemini_client_id
        client_secret = config.gemini_client_secret
        code, _, token_data = make_request(
            f"{base_url}/token",
            method="POST",
            data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
        )
        assert code == 200, f"Expected 200 for valid token, got {code}"
        access_token = token_data.get("access_token")
        assert access_token, "No access_token returned"
        print("[+] OAuth Token Issuance: PASS")

        # 10. Test MCP Initialize Session
        print("[*] Step 10: Testing MCP Session Initialization (Streamable HTTP)...")
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "AntigravityAcceptanceClient", "version": "1.0"},
            },
        }
        code, headers, init_resp = make_request(
            f"{base_url}/mcp",
            method="POST",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            data=init_payload,
        )
        assert code == 200, f"Expected 200 for initialize, got {code}"
        session_id = headers.get("mcp-session-id") or headers.get("Mcp-Session-Id")
        assert session_id, "Missing mcp-session-id header in initialize response"
        print(f"[+] MCP Session Initialized: PASS (Session ID: {session_id[:8]}...)")

        # Send notifications/initialized as required by MCP spec
        code, _, _ = make_request(
            f"{base_url}/mcp",
            method="POST",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "mcp-session-id": session_id,
            },
            data={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        assert code in (200, 202, 204), f"Unexpected code for initialized notification: {code}"

        # 11. Test MCP Tools List
        print("[*] Step 11: Testing MCP Tools Discovery (tools/list)...")
        tools_payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        code, _, tools_resp = make_request(
            f"{base_url}/mcp",
            method="POST",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "mcp-session-id": session_id,
            },
            data=tools_payload,
        )
        assert code == 200, f"Expected 200 for tools/list, got {code}"
        tools_list = tools_resp.get("result", {}).get("tools", [])
        assert len(tools_list) == 11, f"Expected 11 tools, got {len(tools_list)}"
        tool_names = [t.get("name") for t in tools_list]
        print(f"[+] Tools Discovery: PASS ({len(tool_names)} tools: {', '.join(tool_names[:4])}...)")

        # 12. Test MCP Tool Call (Live Frappe Cloud)
        print("[*] Step 12: Testing MCP Tool Call against live Frappe Cloud (get_today_leads)...")
        call_payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_today_leads", "arguments": {}},
        }
        code, _, call_resp = make_request(
            f"{base_url}/mcp",
            method="POST",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "mcp-session-id": session_id,
            },
            data=call_payload,
        )
        assert code == 200, f"Expected 200 for tools/call, got {code}"
        result_content = call_resp.get("result", {}).get("content", [])
        assert result_content, "Expected result.content in tool response"
        tool_result_text = result_content[0].get("text", "")
        tool_data = json.loads(tool_result_text)
        assert tool_data.get("success") is True, f"Tool reported failure: {tool_data}"
        print(f"[+] Tool Execution: PASS (Retrieved {tool_data.get('total')} live leads from Frappe Cloud)")

        # 13. Test Token Revocation
        print("[*] Step 13: Testing Token Revocation (/revoke)...")
        req = urllib.request.Request(
            f"{base_url}/revoke",
            data=urllib.parse.urlencode({"token": access_token}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.status == 200
        print("[+] Token Revocation Endpoint: PASS")

        # Verify revoked token is now rejected
        code, _, _ = make_request(
            f"{base_url}/mcp",
            method="POST",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            data={"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}},
        )
        assert code == 401, f"Expected 401 for revoked token, got {code}"
        print("[+] Revoked Token Rejection: PASS")

    finally:
        # 14. Terminate process cleanly
        print(f"[*] Step 14: Terminating server process (PID {server_proc.pid})...")
        server_proc.terminate()
        try:
            server_proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            server_proc.kill()
            server_proc.wait()

        # 15. Verify port is completely free and no process remains
        print(f"[*] Step 15: Verifying port {port} is completely free...")
        time.sleep(0.5)
        in_use = is_port_in_use(port)
        assert not in_use, f"Port {port} is still in use after server shutdown!"
        print("[+] Process Cleanup: PASS (Zero lingering processes or bound ports)")

    print("=" * 80)
    print("LOCAL ACCEPTANCE RESULT: PASS (100% SUCCESS)")
    print("Dynamic Port, Streamable HTTP, OAuth 2.0, Live Frappe Tools & Cleanup Verified.")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(run_local_acceptance())
