"""
Comprehensive Test Suite for Streamable HTTP (/mcp) and OAuth 2.0 Discovery.
Verifies compatibility with Google Gemini Spark custom connected apps:
1. Health check (/health)
2. OAuth Protected Resource Metadata (RFC 9728)
3. OAuth Authorization Server Metadata (RFC 8414)
4. Dynamic Client Registration (RFC 7591)
5. OAuth Client Credentials Grant (RFC 6749)
6. OAuth Authorization Code Grant (RFC 6749 with PKCE)
7. Unauthenticated MCP endpoint rejection with WWW-Authenticate header
8. Authenticated MCP protocol session (initialize, tools/list, tools/call)
9. Tool read-only annotations validation
10. Fallback MCP_AUTH_TOKEN compatibility
11. Security & credential isolation checks
"""

import os
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.testclient import TestClient
from config import config
from server import create_app
import auth


class TestStreamableHttpAndOAuth(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = TestClient(cls.app, base_url="http://127.0.0.1:8000")
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    # =========================================================================
    # 1. Health Check Tests
    # =========================================================================
    def test_01_health_check(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("service"), "frappe-crm-mcp")
        self.assertEqual(data.get("transport"), "streamable-http")
        self.assertEqual(data.get("tools_count"), 11)
        self.assertIn("tools", data)
        self.assertEqual(len(data["tools"]), 11)

        # Ensure no secrets leak
        raw = res.text
        self.assertNotIn(config.frappe_api_key, raw)
        self.assertNotIn(config.frappe_api_secret, raw)
        if config.mcp_auth_token:
            self.assertNotIn(config.mcp_auth_token, raw)
        self.assertNotIn(config.gemini_client_secret, raw)

    # =========================================================================
    # 2. OAuth Metadata Discovery (RFC 9728 & RFC 8414)
    # =========================================================================
    def test_02_oauth_protected_resource_metadata(self):
        # Test /.well-known/oauth-protected-resource
        res1 = self.client.get("/.well-known/oauth-protected-resource")
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertTrue(data1.get("resource").endswith("/mcp"))
        self.assertIn("authorization_servers", data1)
        self.assertIn("mcp:read", data1.get("scopes_supported", []))

        # Test /.well-known/oauth-protected-resource/mcp
        res2 = self.client.get("/.well-known/oauth-protected-resource/mcp")
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertEqual(data1["resource"], data2["resource"])

    def test_03_oauth_authorization_server_metadata(self):
        # Test /.well-known/oauth-authorization-server
        res1 = self.client.get("/.well-known/oauth-authorization-server")
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertTrue(data1.get("token_endpoint").endswith("/token"))
        self.assertTrue(data1.get("authorization_endpoint").endswith("/authorize"))
        self.assertIn("client_credentials", data1.get("grant_types_supported", []))
        self.assertIn("authorization_code", data1.get("grant_types_supported", []))

        # Test /.well-known/openid-configuration alias
        res2 = self.client.get("/.well-known/openid-configuration")
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res1.json(), res2.json())

    # =========================================================================
    # 3. Dynamic Client Registration (RFC 7591)
    # =========================================================================
    def test_04_dynamic_client_registration(self):
        res = self.client.post(
            "/register",
            json={
                "client_name": "Gemini Automated Connector",
                "redirect_uris": ["https://gemini.google.com/callback"],
                "grant_types": ["client_credentials", "authorization_code"],
            },
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertIn("client_id", data)
        self.assertIn("client_secret", data)
        self.assertEqual(data["client_name"], "Gemini Automated Connector")

        # Test that newly registered client can obtain an access token
        token_res = self.client.post(
            "/token",
            data={
                "grant_type": "client_credentials",
                "client_id": data["client_id"],
                "client_secret": data["client_secret"],
            },
        )
        self.assertEqual(token_res.status_code, 200)
        token_data = token_res.json()
        self.assertIn("access_token", token_data)
        self.assertEqual(token_data["token_type"], "Bearer")

    # =========================================================================
    # 4. OAuth Client Credentials Grant (Pre-configured Gemini Client)
    # =========================================================================
    def test_05_client_credentials_success(self):
        res = self.client.post(
            "/token",
            data={
                "grant_type": "client_credentials",
                "client_id": config.gemini_client_id,
                "client_secret": config.gemini_client_secret,
                "scope": "mcp:read crm:read",
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("access_token", data)
        self.assertEqual(data.get("token_type"), "Bearer")
        self.assertGreater(data.get("expires_in", 0), 0)

    def test_06_client_credentials_invalid_secret(self):
        res = self.client.post(
            "/token",
            data={
                "grant_type": "client_credentials",
                "client_id": config.gemini_client_id,
                "client_secret": "wrong_secret_12345",
            },
        )
        self.assertEqual(res.status_code, 401)
        data = res.json()
        self.assertEqual(data.get("error"), "invalid_client")

    def test_07_client_credentials_unknown_client(self):
        res = self.client.post(
            "/token",
            data={
                "grant_type": "client_credentials",
                "client_id": "nonexistent-client",
                "client_secret": "any_secret",
            },
        )
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json().get("error"), "invalid_client")

    # =========================================================================
    # 5. OAuth Authorization Code Grant
    # =========================================================================
    def test_08_authorization_code_flow(self):
        # 1. Authorize step
        auth_res = self.client.get(
            "/authorize",
            params={
                "response_type": "code",
                "client_id": config.gemini_client_id,
                "redirect_uri": "https://gemini.google.com/oauth/callback",
                "state": "xyz123",
            },
            follow_redirects=False,
        )
        self.assertEqual(auth_res.status_code, 302)
        location = auth_res.headers.get("location", "")
        self.assertIn("code=", location)
        self.assertIn("state=xyz123", location)

        # Extract code from query params
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(location)
        code = parse_qs(parsed.query)["code"][0]

        # 2. Token exchange step
        token_res = self.client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": config.gemini_client_id,
                "client_secret": config.gemini_client_secret,
                "redirect_uri": "https://gemini.google.com/oauth/callback",
            },
        )
        self.assertEqual(token_res.status_code, 200)
        token_data = token_res.json()
        self.assertIn("access_token", token_data)
        self.assertIn("refresh_token", token_data)

    # =========================================================================
    # 6. Streamable HTTP Unauthenticated Protection
    # =========================================================================
    def test_09_mcp_unauthenticated_returns_401_with_www_authenticate(self):
        res = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            headers={"Content-Type": "application/json", "Host": "127.0.0.1"},
        )
        self.assertEqual(res.status_code, 401)
        www_auth = res.headers.get("www-authenticate", "")
        self.assertTrue(www_auth.startswith("Bearer "))
        self.assertIn("resource_metadata=", www_auth)

    def test_10_mcp_invalid_token_returns_401(self):
        res = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            headers={
                "Authorization": "Bearer invalid_garbage_token_value",
                "Content-Type": "application/json",
                "Host": "127.0.0.1",
            },
        )
        self.assertEqual(res.status_code, 401)

    # =========================================================================
    # 7. Streamable HTTP Authenticated Protocol Session
    # =========================================================================
    def test_11_mcp_full_session_with_oauth_token(self):
        # 1. Obtain OAuth Token
        token_res = self.client.post(
            "/token",
            data={
                "grant_type": "client_credentials",
                "client_id": config.gemini_client_id,
                "client_secret": config.gemini_client_secret,
            },
        )
        self.assertEqual(token_res.status_code, 200)
        access_token = token_res.json()["access_token"]
        auth_header = f"Bearer {access_token}"

        # 2. MCP Initialize
        init_res = self.client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "google-gemini", "version": "1.0.0"},
                },
            },
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Host": "127.0.0.1",
            },
        )
        self.assertEqual(init_res.status_code, 200)
        session_id = init_res.headers.get("mcp-session-id")
        self.assertIsNotNone(session_id)
        self.assertIn("result", init_res.text)

        # 3. MCP Initialized Notification
        notif_res = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Host": "127.0.0.1",
                "mcp-session-id": session_id,
            },
        )
        self.assertIn(notif_res.status_code, (200, 202))

        # 4. MCP tools/list
        list_res = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Host": "127.0.0.1",
                "mcp-session-id": session_id,
            },
        )
        self.assertEqual(list_res.status_code, 200)
        body = list_res.text
        self.assertIn("get_today_leads", body)
        self.assertIn("get_management_summary", body)
        self.assertIn('"readOnlyHint":true', body)

        # 5. MCP tools/call (Live query: get_today_leads)
        call_res = self.client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "get_today_leads", "arguments": {}},
            },
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Host": "127.0.0.1",
                "mcp-session-id": session_id,
            },
        )
        self.assertEqual(call_res.status_code, 200)
        import json
        lines = [line for line in call_res.text.splitlines() if line.startswith("data: ")]
        self.assertTrue(len(lines) > 0)
        rpc_data = json.loads(lines[0][6:])
        self.assertEqual(rpc_data.get("id"), 3)
        self.assertIn("result", rpc_data)
        inner_content = json.loads(rpc_data["result"]["content"][0]["text"])
        self.assertTrue(inner_content.get("success"))
        self.assertIn("leads", inner_content)
        self.assertIsInstance(inner_content["leads"], list)

    # =========================================================================
    # 8. Fallback MCP_AUTH_TOKEN Compatibility
    # =========================================================================
    def test_12_mcp_session_with_fallback_token(self):
        if not config.mcp_auth_token:
            self.skipTest("MCP_AUTH_TOKEN not set")

        auth_header = f"Bearer {config.mcp_auth_token}"

        init_res = self.client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 10,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "internal-tester", "version": "1.0.0"},
                },
            },
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Host": "127.0.0.1",
            },
        )
        self.assertEqual(init_res.status_code, 200)
        session_id = init_res.headers.get("mcp-session-id")
        self.assertIsNotNone(session_id)


# =========================================================================
    # 9. Management Summary Tool over Streamable HTTP
    # =========================================================================
    def test_13_mcp_call_management_summary(self):
        token_res = self.client.post(
            "/token",
            data={
                "grant_type": "client_credentials",
                "client_id": config.gemini_client_id,
                "client_secret": config.gemini_client_secret,
            },
        )
        access_token = token_res.json()["access_token"]
        auth_header = f"Bearer {access_token}"

        # Initialize
        init_res = self.client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "gemini-mgmt-test", "version": "1.0.0"},
                },
            },
            headers={"Authorization": auth_header, "Content-Type": "application/json", "Host": "127.0.0.1"},
        )
        session_id = init_res.headers.get("mcp-session-id")

        # Initialized notification
        self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers={"Authorization": auth_header, "Content-Type": "application/json", "Host": "127.0.0.1", "mcp-session-id": session_id},
        )

        # Call get_management_summary
        import json
        call_res = self.client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 20,
                "method": "tools/call",
                "params": {"name": "get_management_summary", "arguments": {}},
            },
            headers={"Authorization": auth_header, "Content-Type": "application/json", "Host": "127.0.0.1", "mcp-session-id": session_id},
        )
        self.assertEqual(call_res.status_code, 200)
        lines = [line for line in call_res.text.splitlines() if line.startswith("data: ")]
        self.assertTrue(len(lines) > 0)
        rpc_data = json.loads(lines[0][6:])
        inner = json.loads(rpc_data["result"]["content"][0]["text"])
        self.assertTrue(inner.get("success"))
        self.assertIn("summary_title", inner)
        self.assertIn("leads", inner)

    # =========================================================================
    # 10. CORS Preflight Tests
    # =========================================================================
    def test_14_cors_preflight(self):
        for path in ("/health", "/mcp", "/.well-known/oauth-protected-resource", "/token"):
            res = self.client.options(
                path,
                headers={
                    "Origin": "https://gemini.google.com",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "authorization,content-type",
                    "Host": "127.0.0.1",
                },
            )
            self.assertIn(res.status_code, (200, 204))
            self.assertTrue(res.headers.get("access-control-allow-origin") is not None)

    # =========================================================================
    # 11. Token Revocation Test (RFC 7009)
    # =========================================================================
    def test_15_token_revocation(self):
        token_res = self.client.post(
            "/token",
            data={
                "grant_type": "client_credentials",
                "client_id": config.gemini_client_id,
                "client_secret": config.gemini_client_secret,
            },
        )
        access_token = token_res.json()["access_token"]

        # Revoke the token
        rev_res = self.client.post("/revoke", data={"token": access_token})
        self.assertEqual(rev_res.status_code, 200)

        # Attempt to use revoked token at /mcp
        mcp_res = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 99, "method": "initialize"},
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json", "Host": "127.0.0.1"},
        )
        self.assertEqual(mcp_res.status_code, 401)


    # =========================================================================
    # 12. Root GET & Dynamic Resource Metadata Header Tests
    # =========================================================================
    def test_16_root_discovery(self):
        """Verify GET / returns 200 with service info and discovery endpoints."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("service"), "frappe-crm-mcp")
        self.assertEqual(data.get("transport"), "streamable-http")
        self.assertIn("endpoints", data)
        self.assertIn("mcp", data["endpoints"])
        self.assertIn("authorization_server", data["endpoints"])
        self.assertIn("protected_resource", data["endpoints"])
        self.assertTrue(res.headers.get("link") is not None)

    def test_17_dynamic_resource_metadata_header(self):
        """Verify unauthenticated /mcp returns WWW-Authenticate with dynamic HTTPS resource_metadata."""
        # Unauthenticated request simulating Cloudflare tunnel proxy
        res = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            headers={
                "Host": "custom-tunnel.example.com",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "custom-tunnel.example.com",
            },
        )
        self.assertEqual(res.status_code, 401)
        www_auth = res.headers.get("www-authenticate", "")
        self.assertIn("Bearer", www_auth)
        self.assertIn("resource_metadata=", www_auth)
        self.assertIn("https://", www_auth)
        # Should not point to 127.0.0.1
        self.assertNotIn("http://127.0.0.1", www_auth)


if __name__ == "__main__":
    unittest.main(verbosity=2)
