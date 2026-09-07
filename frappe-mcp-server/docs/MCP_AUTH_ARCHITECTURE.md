# MCP OAuth 2.0 & Discovery Architecture

This document details the OAuth 2.0 authorization and discovery architecture implemented in the Frappe CRM MCP server for compatibility with Google Gemini Spark and modern MCP clients.

---

## 1. Discovery Endpoints (RFC 9728 & RFC 8414)

### 1.1 Protected Resource Metadata (RFC 9728)
- **Path**: `/.well-known/oauth-protected-resource` and `/.well-known/oauth-protected-resource/mcp`
- **Purpose**: Informs MCP clients (Gemini) about the resource URI and the authoritative authorization servers.
- **Example Response**:
```json
{
  "resource": "https://crm-mcp.example.com/mcp",
  "authorization_servers": ["https://crm-mcp.example.com"],
  "scopes_supported": ["mcp:read", "crm:read"],
  "bearer_methods_supported": ["header"],
  "resource_name": "Frappe CRM MCP Reporting Server",
  "resource_documentation": "https://crm-mcp.example.com/health"
}
```

### 1.2 Authorization Server Metadata (RFC 8414)
- **Path**: `/.well-known/oauth-authorization-server` and `/.well-known/openid-configuration`
- **Purpose**: Declares authorization endpoints, token endpoints, supported grant types, and token auth methods.
- **Example Response**:
```json
{
  "issuer": "https://crm-mcp.example.com",
  "authorization_endpoint": "https://crm-mcp.example.com/authorize",
  "token_endpoint": "https://crm-mcp.example.com/token",
  "registration_endpoint": "https://crm-mcp.example.com/register",
  "revocation_endpoint": "https://crm-mcp.example.com/revoke",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "client_credentials", "refresh_token"],
  "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
  "code_challenge_methods_supported": ["S256", "plain"],
  "scopes_supported": ["mcp:read", "crm:read"]
}
```

---

## 2. Token Issuance & Verification

### 2.1 Supported Grants
1. **Client Credentials (`grant_type=client_credentials`)**:
   - Used by Google Gemini Spark Custom Connected Apps via **Advanced settings**.
   - Validates `client_id` and `client_secret` against the registered client store.
   - Issues an HMAC-SHA256 signed JWT with 1-hour expiration.
2. **Authorization Code (`grant_type=authorization_code`)**:
   - Standard browser consent redirect flow supporting PKCE (RFC 7636).
3. **Refresh Token (`grant_type=refresh_token`)**:
   - Allows long-lived sessions to renew access tokens without re-authenticating.

### 2.2 Token Verifier (`FrappeTokenVerifier`)
When an incoming request hits `/mcp`:
1. If no `Authorization` header is present:
   - Responds with `HTTP 401 Unauthorized`.
   - Sends header: `WWW-Authenticate: Bearer error="invalid_token", error_description="Authentication required", resource_metadata="<url>/.well-known/oauth-protected-resource/mcp"`.
2. If token is signed JWT:
   - Validates signature using `OAUTH_JWT_SECRET`.
   - Checks expiration (`exp`) and revocation (`jti`).
   - Populates `AccessToken(client_id=..., scopes=...)`.
3. If token matches `MCP_AUTH_TOKEN`:
   - Accepts as internal fallback bearer token.
4. If token is invalid or expired:
   - Returns `HTTP 401 Unauthorized`.

---

## 3. Credential Isolation Guarantee

```text
┌─────────────────────────┐
│ Google Gemini Spark UI  │
└────────────┬────────────┘
             │ Client ID + Client Secret
             ▼
┌─────────────────────────┐
│ MCP Server (Auth Layer) │
└────────────┬────────────┘
             │ Server-side only (never leaves process)
             ▼
┌─────────────────────────┐
│ Frappe API Key + Secret │
└────────────┬────────────┘
             │ REST HTTPS
             ▼
┌─────────────────────────┐
│ Production Frappe Cloud │
└─────────────────────────┘
```
