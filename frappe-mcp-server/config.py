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
        return os.environ.get("MCP_HOST", "127.0.0.1").strip()

    @property
    def mcp_port(self) -> int:
        self._ensure_loaded()
        try:
            return int(os.environ.get("MCP_PORT", "8000"))
        except ValueError:
            return 8000

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
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    @staticmethod
    def mask_key(val: str) -> str:
        """Safely mask keys for non-sensitive diagnostics without exposing secrets."""
        if not val or len(val) <= 6:
            return "******"
        return f"{val[:3]}...{val[-3:]}"


config = Config()
