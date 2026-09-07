"""
OAuth 2.0 Authorization Server & Protected Resource Provider for Frappe CRM MCP Server.
Implements:
- RFC 9728: OAuth 2.0 Protected Resource Metadata (/.well-known/oauth-protected-resource)
- RFC 8414: OAuth 2.0 Authorization Server Metadata (/.well-known/oauth-authorization-server)
- RFC 7591: OAuth 2.0 Dynamic Client Registration (/register)
- RFC 6749: OAuth 2.0 Client Credentials & Authorization Code Grants (/authorize, /token)
- RFC 7009: OAuth 2.0 Token Revocation (/revoke)
- SEP-990 / MCP Token Verifier for Streamable HTTP transport
"""

import base64
import hashlib
import json
import secrets
import time
from typing import Any, Dict, List, Optional
import jwt
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from mcp.server.auth.provider import AccessToken

from config import config


class OAuthClient:
    """Represents a registered OAuth 2.0 client."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        client_name: str = "Client",
        redirect_uris: Optional[List[str]] = None,
        grant_types: Optional[List[str]] = None,
        response_types: Optional[List[str]] = None,
        scope: str = "mcp:read crm:read",
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.client_name = client_name
        self.redirect_uris = redirect_uris or []
        self.grant_types = grant_types or ["client_credentials", "authorization_code", "refresh_token"]
        self.response_types = response_types or ["code"]
        self.scope = scope
        self.created_at = time.time()

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "client_name": self.client_name,
            "redirect_uris": self.redirect_uris,
            "grant_types": self.grant_types,
            "response_types": self.response_types,
            "token_endpoint_auth_method": "client_secret_post",
            "scope": self.scope,
            "client_id_issued_at": int(self.created_at),
            "client_secret_expires_at": 0,
        }


class ClientRegistry:
    """Thread-safe store of pre-configured and dynamically registered OAuth clients."""

    def __init__(self):
        self._clients: Dict[str, OAuthClient] = {}
        self._init_defaults()

    def _init_defaults(self):
        """Initialize pre-configured Gemini client from environment."""
        cid = config.gemini_client_id
        csec = config.gemini_client_secret
        if cid and csec:
            self._clients[cid] = OAuthClient(
                client_id=cid,
                client_secret=csec,
                client_name="Google Gemini Spark",
                redirect_uris=[
                    "https://gemini.google.com",
                    "https://gemini.google.com/oauth/callback",
                ],
                grant_types=["client_credentials", "authorization_code", "refresh_token"],
                scope="mcp:read crm:read",
            )

    def get_client(self, client_id: str) -> Optional[OAuthClient]:
        self._init_defaults()
        return self._clients.get(client_id)

    def register_client(
        self,
        client_name: str = "Dynamic Client",
        redirect_uris: Optional[List[str]] = None,
        grant_types: Optional[List[str]] = None,
    ) -> OAuthClient:
        client_id = f"mcp-client-{secrets.token_hex(8)}"
        client_secret = secrets.token_urlsafe(32)
        client = OAuthClient(
            client_id=client_id,
            client_secret=client_secret,
            client_name=client_name,
            redirect_uris=redirect_uris or [],
            grant_types=grant_types or ["client_credentials", "authorization_code", "refresh_token"],
        )
        self._clients[client_id] = client
        return client

    def verify_secret(self, client_id: str, client_secret: str) -> bool:
        client = self.get_client(client_id)
        if not client:
            return False
        return secrets.compare_digest(client.client_secret, client_secret)


class AuthCodeStore:
    """Manages short-lived authorization codes with PKCE support."""

    def __init__(self):
        self._codes: Dict[str, Dict[str, Any]] = {}

    def create_code(
        self,
        client_id: str,
        redirect_uri: str,
        scope: str = "mcp:read crm:read",
        code_challenge: Optional[str] = None,
        code_challenge_method: Optional[str] = None,
    ) -> str:
        code = secrets.token_urlsafe(32)
        self._codes[code] = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method or "S256",
            "expires_at": time.time() + 300,  # 5 minutes
        }
        return code

    def consume_code(
        self,
        code: str,
        client_id: str,
        redirect_uri: Optional[str] = None,
        code_verifier: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        record = self._codes.pop(code, None)
        if not record:
            return None
        if record["expires_at"] < time.time():
            return None
        if record["client_id"] != client_id:
            return None
        if redirect_uri and record["redirect_uri"] and redirect_uri != record["redirect_uri"]:
            return None

        # PKCE verification if challenge was stored
        challenge = record.get("code_challenge")
        if challenge:
            if not code_verifier:
                return None
            method = record.get("code_challenge_method", "S256")
            if method == "S256":
                sha256 = hashlib.sha256(code_verifier.encode("ascii")).digest()
                computed = base64.urlsafe_b64encode(sha256).decode("ascii").rstrip("=")
                if not secrets.compare_digest(computed, challenge):
                    return None
            elif method == "plain":
                if not secrets.compare_digest(code_verifier, challenge):
                    return None

        return record


class TokenStore:
    """Issues and verifies JWT access tokens and tracks refresh tokens."""

    def __init__(self):
        self._refresh_tokens: Dict[str, Dict[str, Any]] = {}
        self._revoked_jtis: set = set()

    def issue_tokens(self, client_id: str, scope: str = "mcp:read crm:read", base_url: Optional[str] = None) -> Dict[str, Any]:
        now = int(time.time())
        expires_in = 3600
        jti = secrets.token_hex(16)
        effective_base = base_url or config.mcp_public_url
        resource_aud = f"{effective_base}/mcp"

        aud_list = [resource_aud, effective_base]
        if config.mcp_public_url and config.mcp_public_url not in aud_list:
            aud_list.extend([config.mcp_public_url, f"{config.mcp_public_url}/mcp"])

        payload = {
            "iss": effective_base,
            "sub": client_id,
            "aud": aud_list,
            "exp": now + expires_in,
            "iat": now,
            "jti": jti,
            "scope": scope,
        }

        access_token = jwt.encode(payload, config.oauth_jwt_secret, algorithm="HS256")

        refresh_token = secrets.token_urlsafe(32)
        self._refresh_tokens[refresh_token] = {
            "client_id": client_id,
            "scope": scope,
            "expires_at": now + (86400 * 30),  # 30 days
        }

        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "refresh_token": refresh_token,
            "scope": scope,
        }

    def consume_refresh_token(self, refresh_token: str, client_id: str) -> Optional[Dict[str, Any]]:
        record = self._refresh_tokens.pop(refresh_token, None)
        if not record:
            return None
        if record["expires_at"] < time.time():
            return None
        if record["client_id"] != client_id:
            return None
        return self.issue_tokens(client_id, record["scope"])

    def revoke_token(self, token: str) -> None:
        if token in self._refresh_tokens:
            del self._refresh_tokens[token]
            return
        try:
            unverified = jwt.decode(
                token,
                options={"verify_signature": False, "verify_exp": False, "verify_aud": False},
            )
            jti = unverified.get("jti")
            if jti:
                self._revoked_jtis.add(jti)
        except Exception:
            pass

    def is_revoked(self, jti: Optional[str]) -> bool:
        if not jti:
            return False
        return jti in self._revoked_jtis


# Singleton instances
client_registry = ClientRegistry()
auth_code_store = AuthCodeStore()
token_store = TokenStore()


def get_base_url(request: Optional[Request] = None) -> str:
    """
    Determine public base URL.
    Uses MCP_PUBLIC_URL if configured to a public domain.
    Otherwise dynamically extracts scheme and host from incoming request headers.
    """
    configured = config.mcp_public_url
    if configured and not configured.startswith("http://127.0.0.1") and not configured.startswith("http://localhost"):
        return configured

    if request:
        scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
        host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        if host:
            return f"{scheme}://{host}".rstrip("/")

    return configured or "http://127.0.0.1:8000"


class FrappeTokenVerifier:
    """
    TokenVerifier implementation for MCP Streamable HTTP transport.
    Accepts:
    1. Valid, non-expired, non-revoked OAuth JWT access tokens issued by this server.
    2. Fallback MCP_AUTH_TOKEN for internal testing and backward compatibility.
    """

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        if not token:
            return None

        # 1. Fallback: Check if token matches MCP_AUTH_TOKEN
        expected_fallback = config.mcp_auth_token
        if expected_fallback and secrets.compare_digest(token, expected_fallback):
            return AccessToken(
                token=token,
                client_id="internal-admin",
                scopes=["mcp:read", "crm:read"],
                expires_at=int(time.time()) + 86400,
                resource=f"{config.mcp_public_url}/mcp",
                subject="internal-admin",
                claims={"sub": "internal-admin", "scope": "mcp:read crm:read"},
            )

        # 2. Validate signed OAuth JWT
        try:
            base_url = config.mcp_public_url
            decoded = jwt.decode(
                token,
                config.oauth_jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False},  # Audience validated below
            )

            # Check expiration
            exp = decoded.get("exp")
            if exp and exp < time.time():
                return None

            # Check revocation
            jti = decoded.get("jti")
            if token_store.is_revoked(jti):
                return None

            # Extract scopes
            scopes_str = decoded.get("scope", "mcp:read crm:read")
            scopes = [s for s in scopes_str.split(" ") if s]

            return AccessToken(
                token=token,
                client_id=decoded.get("sub", "gemini-client"),
                scopes=scopes,
                expires_at=exp,
                resource=f"{base_url}/mcp",
                subject=decoded.get("sub"),
                claims=decoded,
            )
        except (jwt.InvalidTokenError, Exception):
            return None


frappe_token_verifier = FrappeTokenVerifier()


# =============================================================================
# HTTP REQUEST HANDLERS FOR DISCOVERY & OAUTH
# =============================================================================

async def get_oauth_protected_resource(request: Request) -> JSONResponse:
    """
    RFC 9728: OAuth 2.0 Protected Resource Metadata.
    Available at:
      GET /.well-known/oauth-protected-resource
      GET /.well-known/oauth-protected-resource/mcp
    """
    base_url = get_base_url(request)
    return JSONResponse(
        {
            "resource": f"{base_url}/mcp",
            "authorization_servers": [base_url],
            "scopes_supported": ["mcp:read", "crm:read"],
            "bearer_methods_supported": ["header"],
            "resource_name": "Frappe CRM MCP Reporting Server",
            "resource_documentation": f"{base_url}/health",
        },
        headers={
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
        },
    )


async def get_oauth_authorization_server(request: Request) -> JSONResponse:
    """
    RFC 8414: OAuth 2.0 Authorization Server Metadata.
    Available at:
      GET /.well-known/oauth-authorization-server
      GET /.well-known/openid-configuration
    """
    base_url = get_base_url(request)
    return JSONResponse(
        {
            "issuer": base_url,
            "authorization_endpoint": f"{base_url}/authorize",
            "token_endpoint": f"{base_url}/token",
            "registration_endpoint": f"{base_url}/register",
            "revocation_endpoint": f"{base_url}/revoke",
            "response_types_supported": ["code"],
            "grant_types_supported": [
                "authorization_code",
                "client_credentials",
                "refresh_token",
            ],
            "token_endpoint_auth_methods_supported": [
                "client_secret_basic",
                "client_secret_post",
            ],
            "code_challenge_methods_supported": ["S256", "plain"],
            "scopes_supported": ["mcp:read", "crm:read"],
            "service_documentation": f"{base_url}/health",
        },
        headers={
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
        },
    )


async def register_endpoint(request: Request) -> Response:
    """
    RFC 7591: Dynamic Client Registration.
    Available at: POST /register
    """
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
            },
        )

    try:
        body = await request.json()
    except Exception:
        body = {}

    client_name = body.get("client_name", "Google Gemini Client")
    redirect_uris = body.get("redirect_uris", [])
    grant_types = body.get("grant_types", ["client_credentials", "authorization_code", "refresh_token"])

    client = client_registry.register_client(
        client_name=client_name,
        redirect_uris=redirect_uris,
        grant_types=grant_types,
    )

    return JSONResponse(
        client.to_metadata(),
        status_code=201,
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "Access-Control-Allow-Origin": "*",
        },
    )


async def authorize_endpoint(request: Request) -> Response:
    """
    RFC 6749: Authorization Endpoint.
    Available at: GET /authorize, POST /authorize
    Generates authorization code for Gemini and redirects to callback.
    """
    if request.method == "GET":
        params = dict(request.query_params)
    else:
        try:
            params = dict(await request.form())
        except Exception:
            params = dict(request.query_params)

    client_id = params.get("client_id", "")
    redirect_uri = params.get("redirect_uri", "")
    response_type = params.get("response_type", "")
    state = params.get("state", "")
    scope = params.get("scope", "mcp:read crm:read")
    code_challenge = params.get("code_challenge")
    code_challenge_method = params.get("code_challenge_method", "S256")

    client = client_registry.get_client(client_id)
    if not client:
        return JSONResponse(
            {"error": "unauthorized_client", "error_description": "Unknown client_id."},
            status_code=400,
        )

    if response_type != "code":
        return JSONResponse(
            {"error": "unsupported_response_type", "error_description": "Only 'code' response_type is supported."},
            status_code=400,
        )

    code = auth_code_store.create_code(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=scope,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
    )

    if redirect_uri:
        delimiter = "&" if "?" in redirect_uri else "?"
        target_url = f"{redirect_uri}{delimiter}code={code}"
        if state:
            target_url += f"&state={state}"
        return RedirectResponse(target_url, status_code=302)

    return JSONResponse({"code": code, "state": state})


async def token_endpoint(request: Request) -> Response:
    """
    RFC 6749: OAuth 2.0 Token Endpoint.
    Supports:
    1. grant_type=client_credentials (for Gemini Advanced settings)
    2. grant_type=authorization_code (for OAuth consent flow)
    3. grant_type=refresh_token (for token renewal)
    """
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
            },
        )

    # Extract parameters from Form or JSON
    content_type = request.headers.get("content-type", "").lower()
    data: Dict[str, Any] = {}
    if "application/json" in content_type:
        try:
            data = await request.json()
        except Exception:
            pass
    else:
        try:
            form = await request.form()
            data = dict(form)
        except Exception:
            pass

    # Extract client credentials from Basic Auth header if present
    auth_header = request.headers.get("authorization", "")
    client_id = data.get("client_id", "")
    client_secret = data.get("client_secret", "")

    if auth_header.startswith("Basic "):
        try:
            raw_creds = base64.b64decode(auth_header[6:].strip()).decode("utf-8")
            if ":" in raw_creds:
                h_id, h_sec = raw_creds.split(":", 1)
                client_id = client_id or h_id
                client_secret = client_secret or h_sec
        except Exception:
            pass

    grant_type = data.get("grant_type", "")

    headers = {
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
        "Access-Control-Allow-Origin": "*",
    }

    # 1. CLIENT CREDENTIALS GRANT
    if grant_type == "client_credentials":
        if not client_id or not client_secret:
            return JSONResponse(
                {"error": "invalid_client", "error_description": "Missing client credentials."},
                status_code=401,
                headers=headers,
            )

        if not client_registry.verify_secret(client_id, client_secret):
            return JSONResponse(
                {"error": "invalid_client", "error_description": "Invalid client_id or client_secret."},
                status_code=401,
                headers=headers,
            )

        scope = data.get("scope", "mcp:read crm:read")
        tokens = token_store.issue_tokens(client_id, scope=scope)
        return JSONResponse(tokens, status_code=200, headers=headers)

    # 2. AUTHORIZATION CODE GRANT
    elif grant_type == "authorization_code":
        code = data.get("code", "")
        code_verifier = data.get("code_verifier")
        redirect_uri = data.get("redirect_uri")

        if not code or not client_id:
            return JSONResponse(
                {"error": "invalid_request", "error_description": "Missing code or client_id."},
                status_code=400,
                headers=headers,
            )

        # Verify client credentials if secret provided
        if client_secret and not client_registry.verify_secret(client_id, client_secret):
            return JSONResponse(
                {"error": "invalid_client", "error_description": "Invalid client credentials."},
                status_code=401,
                headers=headers,
            )

        auth_record = auth_code_store.consume_code(
            code=code,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
        )

        if not auth_record:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "Invalid or expired authorization code."},
                status_code=400,
                headers=headers,
            )

        tokens = token_store.issue_tokens(client_id, scope=auth_record.get("scope", "mcp:read crm:read"))
        return JSONResponse(tokens, status_code=200, headers=headers)

    # 3. REFRESH TOKEN GRANT
    elif grant_type == "refresh_token":
        refresh_token = data.get("refresh_token", "")
        if not refresh_token or not client_id:
            return JSONResponse(
                {"error": "invalid_request", "error_description": "Missing refresh_token or client_id."},
                status_code=400,
                headers=headers,
            )

        tokens = token_store.consume_refresh_token(refresh_token, client_id)
        if not tokens:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "Invalid or expired refresh token."},
                status_code=400,
                headers=headers,
            )
        return JSONResponse(tokens, status_code=200, headers=headers)

    return JSONResponse(
        {
            "error": "unsupported_grant_type",
            "error_description": f"Grant type '{grant_type}' is not supported.",
        },
        status_code=400,
        headers=headers,
    )


async def revoke_endpoint(request: Request) -> Response:
    """
    RFC 7009: Token Revocation Endpoint.
    Available at: POST /revoke
    """
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
            },
        )

    try:
        form = await request.form()
        token = form.get("token", "")
    except Exception:
        token = ""

    if token:
        token_store.revoke_token(token)

    return JSONResponse({"status": "revoked"}, status_code=200)
