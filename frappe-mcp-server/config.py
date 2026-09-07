"""
Configuration loader for Frappe CRM MCP Server.
Loads and validates environment variables securely with dynamic reload support.
Supports both local and remote MCP deployments.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)


class Config:
    """Server configuration values loaded from environment."""

    def _ensure_loaded(self) -> None:
        """Reload .env dynamically if credentials were not present at boot."""
        if not os.environ.get("FRAPPE_API_KEY") or not os.environ.get("FRAPPE_API_SECRET"):
            if env_path.exists():
                load_dotenv(dotenv_path=env_path, override=True)

    @property
    def frappe_base_url(self) -> str:
        self._ensure_loaded()
        url = os.environ.get("FRAPPE_BASE_URL", "https://middleeast.frappe.cloud").strip()
        return url.rstrip("/")

    @property
    def frappe_api_key(self) -> str:
        self._ensure_loaded()
        return os.environ.get("FRAPPE_API_KEY", "").strip()

    @property
    def frappe_api_secret(self) -> str:
        self._ensure_loaded()
        return os.environ.get("FRAPPE_API_SECRET", "").strip()

    @property
    def http_timeout(self) -> float:
        self._ensure_loaded()
        try:
            return float(os.environ.get("HTTP_TIMEOUT", "15.0"))
        except ValueError:
            return 15.0

    @property
    def gemini_api_key(self) -> str:
        self._ensure_loaded()
        return os.environ.get("GEMINI_API_KEY", "").strip()

    @property
    def mcp_auth_token(self) -> str:
        """Optional Bearer token required for remote incoming MCP client connections."""
        self._ensure_loaded()
        return os.environ.get("MCP_AUTH_TOKEN", "").strip()

    @property
    def mcp_host(self) -> str:
        self._ensure_loaded()
        return os.environ.get("MCP_HOST", "0.0.0.0").strip()

    @property
    def mcp_port(self) -> int:
        self._ensure_loaded()
        try:
            return int(os.environ.get("PORT", os.environ.get("MCP_PORT", "8080")))
        except ValueError:
            return 8080

    @property
    def gemini_client_id(self) -> str:
        """Dedicated OAuth Client ID for Gemini Spark connected app."""
        self._ensure_loaded()
        return os.environ.get("GEMINI_CLIENT_ID", "gemini-spark-client").strip()

    @property
    def gemini_client_secret(self) -> str:
        """Dedicated OAuth Client Secret for Gemini Spark connected app."""
        self._ensure_loaded()
        return os.environ.get("GEMINI_CLIENT_SECRET", "").strip()

    @property
    def oauth_jwt_secret(self) -> str:
        """Secret key for signing and verifying OAuth JWT access tokens."""
        self._ensure_loaded()
        return os.environ.get("OAUTH_JWT_SECRET", "").strip()

    @property
    def mcp_public_url(self) -> str:
        """Publicly accessible HTTPS base URL (e.g. https://crm-mcp.example.com)."""
        self._ensure_loaded()
        url = os.environ.get("MCP_PUBLIC_URL", "").strip()
        if url:
            return url.rstrip("/")
        return f"http://{self.mcp_host}:{self.mcp_port}"

    @property
    def allowed_hosts(self) -> list[str]:
        """Allowed host header values for DNS rebinding protection."""
        self._ensure_loaded()
        hosts = [
            "127.0.0.1",
            "127.0.0.1:*",
            "localhost",
            "localhost:*",
            "[::1]",
            "[::1]:*",
            "testserver",
            "testserver:*",
            "*.trycloudflare.com",
            "*.trycloudflare.com:*",
            "*.run.app",
            "*.run.app:*",
        ]
        custom_hosts = os.environ.get("MCP_ALLOWED_HOSTS", "").strip()
        if custom_hosts:
            for h in custom_hosts.split(","):
                h = h.strip()
                if h and h not in hosts:
                    hosts.append(h)
        if self.mcp_public_url:
            from urllib.parse import urlparse
            parsed = urlparse(self.mcp_public_url)
            if parsed.hostname and parsed.hostname not in hosts:
                hosts.append(parsed.hostname)
                hosts.append(f"{parsed.hostname}:*")
        return hosts

    @property
    def allowed_origins(self) -> list[str]:
        """Allowed origin headers for CORS and DNS rebinding protection."""
        self._ensure_loaded()
        origins = [
            "https://gemini.google.com",
            "http://127.0.0.1:*",
            "http://127.0.0.1",
            "http://localhost:*",
            "http://localhost",
            "http://testserver",
        ]
        custom_origins = os.environ.get("MCP_ALLOWED_ORIGINS", "").strip()
        if custom_origins:
            for o in custom_origins.split(","):
                o = o.strip()
                if o and o not in origins:
                    origins.append(o)
        if self.mcp_public_url and self.mcp_public_url not in origins:
            origins.append(self.mcp_public_url)
        return origins

    @property
    def is_configured(self) -> bool:
        """Check if required Frappe credentials are present."""
        return bool(self.frappe_base_url and self.frappe_api_key and self.frappe_api_secret)

    def validate(self) -> None:
        """Raise ValueError if required configuration is missing."""
        missing = []
        if not self.frappe_base_url:
            missing.append("FRAPPE_BASE_URL")
        if not self.frappe_api_key:
            missing.append("FRAPPE_API_KEY")
        if not self.frappe_api_secret:
            missing.append("FRAPPE_API_SECRET")
        if not self.gemini_client_secret:
            missing.append("GEMINI_CLIENT_SECRET")
        if not self.oauth_jwt_secret:
            missing.append("OAUTH_JWT_SECRET")
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    @staticmethod
    def mask_key(val: str) -> str:
        """Safely mask keys for non-sensitive diagnostics without exposing secrets."""
        if not val or len(val) <= 6:
            return "******"
        return f"{val[:3]}...{val[-3:]}"


config = Config()
