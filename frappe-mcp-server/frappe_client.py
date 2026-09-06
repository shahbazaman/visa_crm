"""
Secure HTTPS Client for Frappe CRM MCP Server.
Connects strictly to visa_crm.api.mcp.get_today_leads with controlled validation.
"""

from typing import Any, Dict, List, Optional
import httpx
from config import config


REQUIRED_LEAD_FIELDS = [
    "name",
    "customer_name",
    "email",
    "phone",
    "status",
    "source",
    "creation",
    "assigned_counselor",
    "department",
]


class FrappeClientError(Exception):
    pass


class FrappeUnavailableError(FrappeClientError):
    pass


class FrappeAuthError(FrappeClientError):
    pass


class FrappePermissionError(FrappeClientError):
    pass


class FrappeResponseError(FrappeClientError):
    pass


class FrappeTimeoutError(FrappeClientError):
    pass


class FrappeClient:
    """Client for querying the whitelisted Frappe CRM MCP API."""

    ENDPOINT_PATH = "/api/method/visa_crm.api.mcp.get_today_leads"

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self._override_base_url = base_url
        self._override_api_key = api_key
        self._override_api_secret = api_secret
        self._override_timeout = timeout

    @property
    def base_url(self) -> str:
        return (self._override_base_url or config.frappe_base_url).rstrip("/")

    @property
    def api_key(self) -> str:
        return self._override_api_key or config.frappe_api_key

    @property
    def api_secret(self) -> str:
        return self._override_api_secret or config.frappe_api_secret

    @property
    def timeout(self) -> float:
        return self._override_timeout if self._override_timeout is not None else config.http_timeout

    def _get_headers(self) -> Dict[str, str]:
        """Construct authorization headers dynamically without exposing secrets."""
        key = self.api_key
        secret = self.api_secret
        if not key or not secret:
            raise FrappeAuthError("Frappe CRM authentication credentials are not configured.")
        return {
            "Authorization": f"token {key}:{secret}",
            "Accept": "application/json",
            "User-Agent": "Frappe-MCP-Server/1.0",
        }

    def _validate_response_schema(self, data: Any) -> Dict[str, Any]:
        """
        Validates the strict Phase 1 response schema:
        { "message": { "success": true, "date": "YYYY-MM-DD", "total": N, "leads": [...] } }
        """
        if not isinstance(data, dict):
            raise FrappeResponseError("Frappe returned an unexpected response format.")

        envelope = data.get("message")
        if not isinstance(envelope, dict):
            raise FrappeResponseError("Frappe returned an unexpected response format.")

        if envelope.get("success") is not True:
            raise FrappeResponseError("Frappe returned an unexpected response format.")

        if "date" not in envelope or not isinstance(envelope["date"], str):
            raise FrappeResponseError("Frappe returned an unexpected response format.")

        if "total" not in envelope or not isinstance(envelope["total"], int):
            raise FrappeResponseError("Frappe returned an unexpected response format.")

        leads = envelope.get("leads")
        if not isinstance(leads, list):
            raise FrappeResponseError("Frappe returned an unexpected response format.")

        validated_leads: List[Dict[str, Any]] = []
        for item in leads:
            if not isinstance(item, dict):
                raise FrappeResponseError("Frappe returned an unexpected response format.")

            for field in REQUIRED_LEAD_FIELDS:
                if field not in item:
                    raise FrappeResponseError("Frappe returned an unexpected response format.")

            lead_record = {field: item.get(field) for field in REQUIRED_LEAD_FIELDS}
            validated_leads.append(lead_record)

        return {
            "success": True,
            "date": envelope["date"],
            "total": envelope["total"],
            "leads": validated_leads,
        }

    async def get_today_leads(self) -> Dict[str, Any]:
        """
        Asynchronously fetches today's CRM leads from the production Frappe instance.
        """
        url = f"{self.base_url}{self.ENDPOINT_PATH}"

        try:
            headers = self._get_headers()
        except FrappeAuthError:
            raise FrappeAuthError("Frappe CRM authentication failed.")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers)
        except httpx.TimeoutException:
            raise FrappeTimeoutError("Frappe CRM request timed out.")
        except httpx.NetworkError:
            raise FrappeUnavailableError("Frappe CRM is currently unavailable.")
        except Exception:
            raise FrappeUnavailableError("Frappe CRM is currently unavailable.")

        if response.status_code == 401:
            raise FrappeAuthError("Frappe CRM authentication failed.")

        if response.status_code == 403:
            body_text = response.text.lower()
            if "authentication" in body_text or "guest" in body_text:
                raise FrappeAuthError("Frappe CRM authentication failed.")
            raise FrappePermissionError("The configured Frappe account does not have permission to read CRM Leads.")

        if response.status_code in (502, 503, 504):
            raise FrappeUnavailableError("Frappe CRM is currently unavailable.")

        if response.status_code != 200:
            raise FrappeResponseError("Frappe returned an unexpected response format.")

        try:
            raw_json = response.json()
        except Exception:
            raise FrappeResponseError("Frappe returned an unexpected response format.")

        return self._validate_response_schema(raw_json)

    def get_today_leads_sync(self) -> Dict[str, Any]:
        import asyncio
        return asyncio.run(self.get_today_leads())


frappe_client = FrappeClient()
