"""
Secure HTTPS Client for Frappe CRM MCP Server.
Connects strictly to production Frappe CRM with controlled, read-only reporting queries.
"""

from datetime import datetime
import json
import re
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

LEAD_RESOURCE_FIELDS = [
    "name",
    "lead_name",
    "first_name",
    "last_name",
    "email",
    "mobile_no",
    "phone",
    "status",
    "source",
    "responsible_department",
    "lead_owner",
    "assignment_status",
    "creation",
]

VISA_RESOURCE_FIELDS = [
    "name",
    "applicant_name",
    "customer",
    "lead",
    "visa_type",
    "country",
    "status",
    "submitted_on",
    "decision_on",
    "creation",
]

TODO_RESOURCE_FIELDS = [
    "name",
    "description",
    "status",
    "priority",
    "date",
    "allocated_to",
    "reference_type",
    "reference_name",
    "assigned_by",
    "creation",
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


class FrappeValidationError(FrappeClientError):
    pass


def validate_iso_date(val: Optional[str], field_name: str, required: bool = False) -> Optional[str]:
    """Strictly validate that a date string is in YYYY-MM-DD ISO format."""
    if val is None or (isinstance(val, str) and not val.strip()):
        if required:
            raise FrappeValidationError(
                f"{field_name} is required and cannot be empty."
            )
        return None
    val = val.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", val):
        raise FrappeValidationError(
            f"Invalid {field_name} format. Date must be strictly in YYYY-MM-DD format (e.g. 2026-09-06)."
        )
    try:
        datetime.strptime(val, "%Y-%m-%d")
    except ValueError:
        raise FrappeValidationError(
            f"Invalid calendar date for {field_name}. Please provide a valid calendar day."
        )
    return val


def format_lead_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Project a raw Frappe CRM Lead record into the standard, controlled schema."""
    customer_name = (
        rec.get("lead_name")
        or f"{rec.get('first_name') or ''} {rec.get('last_name') or ''}".strip()
        or rec.get("name")
    )
    phone = rec.get("mobile_no") or rec.get("phone") or None
    counselor = rec.get("lead_owner")
    if counselor in (None, "", "Administrator", "Guest"):
        counselor = None

    return {
        "name": rec.get("name"),
        "customer_name": customer_name,
        "email": rec.get("email") or None,
        "phone": phone,
        "status": rec.get("status") or None,
        "source": rec.get("source") or None,
        "department": rec.get("responsible_department") or rec.get("department") or None,
        "assigned_counselor": counselor,
        "creation": str(rec.get("creation")),
    }


class FrappeClient:
    """Client for querying the production Frappe CRM reporting APIs."""

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

    async def _query_resource(
        self,
        doctype: str,
        fields: List[str],
        filters: Optional[List[Any]] = None,
        order_by: str = "creation desc",
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        Internal controlled query against Frappe REST resource API.
        Enforces server-side authentication, predefined fields, and safe limits.
        """
        url = f"{self.base_url}/api/resource/{doctype}"
        safe_limit = max(1, min(int(limit), 500))
        params: Dict[str, str] = {
            "fields": json.dumps(fields),
            "order_by": order_by,
            "limit_page_length": str(safe_limit),
        }
        if filters:
            params["filters"] = json.dumps(filters)

        try:
            headers = self._get_headers()
        except FrappeAuthError:
            raise FrappeAuthError("Frappe CRM authentication failed.")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers, params=params)
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
            raise FrappePermissionError(f"Insufficient permissions to read {doctype} records.")

        if response.status_code in (502, 503, 504):
            raise FrappeUnavailableError("Frappe CRM is currently unavailable.")

        if response.status_code != 200:
            raise FrappeResponseError(f"Frappe query failed with status {response.status_code}.")

        try:
            data = response.json()
            return data.get("data", [])
        except Exception:
            raise FrappeResponseError("Failed to parse Frappe CRM response.")

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

    # =========================================================================
    # TOOL 1: get_today_leads (Phase 1 endpoint, kept intact)
    # =========================================================================
    async def get_today_leads(self) -> Dict[str, Any]:
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

    # =========================================================================
    # TOOL 2: get_leads_by_date
    # =========================================================================
    async def get_leads_by_date(self, date: str) -> Dict[str, Any]:
        valid_date = validate_iso_date(date, "date", required=True)
        filters = [
            ["creation", ">=", f"{valid_date} 00:00:00"],
            ["creation", "<=", f"{valid_date} 23:59:59"],
        ]
        raw_leads = await self._query_resource("CRM Lead", LEAD_RESOURCE_FIELDS, filters)
        leads = [format_lead_record(r) for r in raw_leads]
        return {
            "success": True,
            "date": valid_date,
            "total": len(leads),
            "leads": leads,
        }

    # =========================================================================
    # TOOL 3: get_lead_report
    # =========================================================================
    async def get_lead_report(self, start_date: str, end_date: str) -> Dict[str, Any]:
        valid_start = validate_iso_date(start_date, "start_date", required=True)
        valid_end = validate_iso_date(end_date, "end_date", required=True)
        if valid_start > valid_end:
            raise FrappeValidationError(
                f"start_date '{valid_start}' cannot be after end_date '{valid_end}'."
            )

        filters = [
            ["creation", ">=", f"{valid_start} 00:00:00"],
            ["creation", "<=", f"{valid_end} 23:59:59"],
        ]
        raw_leads = await self._query_resource("CRM Lead", LEAD_RESOURCE_FIELDS, filters)
        leads = [format_lead_record(r) for r in raw_leads]

        by_dept: Dict[str, int] = {}
        by_source: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        assigned_count = 0
        unassigned_count = 0

        for l in leads:
            d = l.get("department") or "Unspecified"
            by_dept[d] = by_dept.get(d, 0) + 1

            s = l.get("source") or "Unspecified"
            by_source[s] = by_source.get(s, 0) + 1

            st = l.get("status") or "Unspecified"
            by_status[st] = by_status.get(st, 0) + 1

            if l.get("assigned_counselor"):
                assigned_count += 1
            else:
                unassigned_count += 1

        return {
            "success": True,
            "start_date": valid_start,
            "end_date": valid_end,
            "total_leads": len(leads),
            "leads_by_department": by_dept,
            "leads_by_source": by_source,
            "leads_by_status": by_status,
            "assigned_vs_unassigned": {
                "assigned": assigned_count,
                "unassigned": unassigned_count,
            },
            "leads": leads,
        }

    # =========================================================================
    # TOOL 4: get_leads_by_department
    # =========================================================================
    async def get_leads_by_department(self, department: str) -> Dict[str, Any]:
        if not department or not department.strip():
            raise FrappeValidationError("department parameter cannot be empty.")
        dept_query = department.strip()
        filters = [["responsible_department", "like", f"%{dept_query}%"]]
        raw_leads = await self._query_resource("CRM Lead", LEAD_RESOURCE_FIELDS, filters)
        leads = [format_lead_record(r) for r in raw_leads]
        return {
            "success": True,
            "department": dept_query,
            "total": len(leads),
            "leads": leads,
        }

    # =========================================================================
    # TOOL 5: get_leads_by_counselor
    # =========================================================================
    async def get_leads_by_counselor(self, counselor: str) -> Dict[str, Any]:
        if not counselor or not counselor.strip():
            raise FrappeValidationError("counselor parameter cannot be empty.")
        counselor_query = counselor.strip()
        filters = [["lead_owner", "like", f"%{counselor_query}%"]]
        raw_leads = await self._query_resource("CRM Lead", LEAD_RESOURCE_FIELDS, filters)
        leads = [format_lead_record(r) for r in raw_leads]
        return {
            "success": True,
            "counselor": counselor_query,
            "total": len(leads),
            "leads": leads,
        }

    # =========================================================================
    # TOOL 6: get_lead_sources
    # =========================================================================
    async def get_lead_sources(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        filters: List[Any] = []
        valid_start = validate_iso_date(start_date, "start_date") if start_date else None
        valid_end = validate_iso_date(end_date, "end_date") if end_date else None

        if valid_start and valid_end and valid_start > valid_end:
            raise FrappeValidationError(
                f"start_date '{valid_start}' cannot be after end_date '{valid_end}'."
            )

        if valid_start:
            filters.append(["creation", ">=", f"{valid_start} 00:00:00"])
        if valid_end:
            filters.append(["creation", "<=", f"{valid_end} 23:59:59"])

        raw_leads = await self._query_resource("CRM Lead", ["name", "source"], filters or None)
        sources: Dict[str, int] = {}
        for r in raw_leads:
            src = r.get("source") or "Unspecified"
            sources[src] = sources.get(src, 0) + 1

        return {
            "success": True,
            "start_date": valid_start,
            "end_date": valid_end,
            "total": len(raw_leads),
            "sources": sources,
        }

    # =========================================================================
    # TOOL 7: get_unassigned_leads
    # =========================================================================
    async def get_unassigned_leads(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        filters: List[Any] = []
        valid_start = validate_iso_date(start_date, "start_date") if start_date else None
        valid_end = validate_iso_date(end_date, "end_date") if end_date else None

        if valid_start and valid_end and valid_start > valid_end:
            raise FrappeValidationError(
                f"start_date '{valid_start}' cannot be after end_date '{valid_end}'."
            )

        if valid_start:
            filters.append(["creation", ">=", f"{valid_start} 00:00:00"])
        if valid_end:
            filters.append(["creation", "<=", f"{valid_end} 23:59:59"])

        raw_leads = await self._query_resource("CRM Lead", LEAD_RESOURCE_FIELDS, filters or None)
        unassigned: List[Dict[str, Any]] = []
        for r in raw_leads:
            owner = r.get("lead_owner")
            status = r.get("assignment_status")
            if status in ("Unassigned", "Needs Assignment") or owner in (None, "", "Administrator", "Guest"):
                unassigned.append(format_lead_record(r))

        return {
            "success": True,
            "start_date": valid_start,
            "end_date": valid_end,
            "total": len(unassigned),
            "unassigned_leads": unassigned,
        }

    # =========================================================================
    # TOOL 8: get_followups
    # =========================================================================
    async def get_followups(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        filters: List[Any] = []
        valid_start = validate_iso_date(start_date, "start_date") if start_date else None
        valid_end = validate_iso_date(end_date, "end_date") if end_date else None

        if valid_start and valid_end and valid_start > valid_end:
            raise FrappeValidationError(
                f"start_date '{valid_start}' cannot be after end_date '{valid_end}'."
            )

        if valid_start:
            filters.append(["creation", ">=", f"{valid_start} 00:00:00"])
        if valid_end:
            filters.append(["creation", "<=", f"{valid_end} 23:59:59"])

        raw_todos = await self._query_resource("ToDo", TODO_RESOURCE_FIELDS, filters or None)
        followups = []
        for t in raw_todos:
            desc = t.get("description") or ""
            ref = t.get("reference_type")
            if ref in ("CRM Lead", "Lead Intake Queue") or "follow" in desc.lower():
                followups.append({
                    "name": t.get("name"),
                    "description": desc,
                    "due_date": str(t.get("date")) if t.get("date") else None,
                    "status": t.get("status"),
                    "assigned_to": t.get("allocated_to"),
                    "linked_crm_record": t.get("reference_name"),
                    "priority": t.get("priority"),
                    "creation": str(t.get("creation")),
                })

        return {
            "success": True,
            "start_date": valid_start,
            "end_date": valid_end,
            "total": len(followups),
            "followups": followups,
        }

    # =========================================================================
    # TOOL 9: get_tasks
    # =========================================================================
    async def get_tasks(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        assigned_employee: Optional[str] = None,
    ) -> Dict[str, Any]:
        filters: List[Any] = []
        valid_start = validate_iso_date(start_date, "start_date") if start_date else None
        valid_end = validate_iso_date(end_date, "end_date") if end_date else None

        if valid_start and valid_end and valid_start > valid_end:
            raise FrappeValidationError(
                f"start_date '{valid_start}' cannot be after end_date '{valid_end}'."
            )

        if valid_start:
            filters.append(["creation", ">=", f"{valid_start} 00:00:00"])
        if valid_end:
            filters.append(["creation", "<=", f"{valid_end} 23:59:59"])
        if assigned_employee and assigned_employee.strip():
            filters.append(["allocated_to", "like", f"%{assigned_employee.strip()}%"])

        raw_todos = await self._query_resource("ToDo", TODO_RESOURCE_FIELDS, filters or None)
        tasks = []
        for t in raw_todos:
            tasks.append({
                "task_name": t.get("name"),
                "subject": t.get("description"),
                "assigned_employee": t.get("allocated_to"),
                "due_date": str(t.get("date")) if t.get("date") else None,
                "status": t.get("status"),
                "linked_crm_record": t.get("reference_name"),
                "priority": t.get("priority"),
            })

        return {
            "success": True,
            "start_date": valid_start,
            "end_date": valid_end,
            "assigned_employee": assigned_employee,
            "total": len(tasks),
            "tasks": tasks,
        }

    # =========================================================================
    # TOOL 10: get_visa_applications
    # =========================================================================
    async def get_visa_applications(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        filters: List[Any] = []
        valid_start = validate_iso_date(start_date, "start_date") if start_date else None
        valid_end = validate_iso_date(end_date, "end_date") if end_date else None

        if valid_start and valid_end and valid_start > valid_end:
            raise FrappeValidationError(
                f"start_date '{valid_start}' cannot be after end_date '{valid_end}'."
            )

        if valid_start:
            filters.append(["creation", ">=", f"{valid_start} 00:00:00"])
        if valid_end:
            filters.append(["creation", "<=", f"{valid_end} 23:59:59"])
        if status and status.strip():
            filters.append(["status", "=", status.strip()])

        raw_visas = await self._query_resource("Visa Application", VISA_RESOURCE_FIELDS, filters or None)
        visas = []
        for v in raw_visas:
            visas.append({
                "name": v.get("name"),
                "applicant_name": v.get("applicant_name"),
                "customer": v.get("customer"),
                "lead": v.get("lead"),
                "visa_type": v.get("visa_type"),
                "country": v.get("country"),
                "status": v.get("status"),
                "submitted_on": str(v.get("submitted_on")) if v.get("submitted_on") else None,
                "decision_on": str(v.get("decision_on")) if v.get("decision_on") else None,
                "creation": str(v.get("creation")),
            })

        return {
            "success": True,
            "start_date": valid_start,
            "end_date": valid_end,
            "status": status,
            "total": len(visas),
            "visa_applications": visas,
        }

    # =========================================================================
    # TOOL 11: get_management_summary (Executive BI Dashboard)
    # =========================================================================
    async def get_management_summary(self, date: Optional[str] = None) -> Dict[str, Any]:
        """
        Generates an aggregated executive management summary across leads, assignments,
        follow-ups, and visa applications for a specific date (defaults to today).
        """
        if date:
            target_date = validate_iso_date(date, "date")
        else:
            target_date = datetime.now().strftime("%Y-%m-%d")

        # 1. Leads on target date
        leads_res = await self.get_leads_by_date(target_date)
        leads_list = leads_res.get("leads", [])
        total_leads = len(leads_list)

        dept_counts: Dict[str, int] = {}
        source_counts: Dict[str, int] = {}
        status_counts: Dict[str, int] = {}
        for l in leads_list:
            d = l.get("department") or "Unspecified"
            dept_counts[d] = dept_counts.get(d, 0) + 1
            s = l.get("source") or "Unspecified"
            source_counts[s] = source_counts.get(s, 0) + 1
            st = l.get("status") or "Unspecified"
            status_counts[st] = status_counts.get(st, 0) + 1

        # 2. Assignment status on target date
        unassigned_res = await self.get_unassigned_leads(target_date, target_date)
        unassigned_list = unassigned_res.get("unassigned_leads", [])
        unassigned_count = len(unassigned_list)
        assigned_count = total_leads - unassigned_count

        # 3. Followups on target date
        followups_res = await self.get_followups(target_date, target_date)
        followups_list = followups_res.get("followups", [])
        open_followups = [f for f in followups_list if f.get("status") == "Open"]

        # 4. Visa Applications created in the month of target date
        month_start = f"{target_date[:7]}-01"
        visas_res = await self.get_visa_applications(month_start, target_date)
        visas_list = visas_res.get("visa_applications", [])

        # 2b. Counselor distribution & backlog rate
        counselor_counts: Dict[str, int] = {}
        for l in leads_list:
            owner = l.get("lead_owner")
            if owner:
                counselor_counts[owner] = counselor_counts.get(owner, 0) + 1
        backlog_rate = f"{(unassigned_count / total_leads * 100):.1f}%" if total_leads > 0 else "0.0%"

        # 3b. Overdue follow-ups
        overdue_followups = [f for f in open_followups if f.get("due_date") and f.get("due_date") < target_date]

        # 3c. Tasks for management overview
        tasks_res = await self.get_tasks()
        tasks_list = tasks_res.get("tasks", [])
        open_tasks = [t for t in tasks_list if t.get("status") == "Open"]

        # 4b. Visa status breakdown
        visa_status_counts: Dict[str, int] = {}
        for v in visas_list:
            st = v.get("status") or "Unspecified"
            visa_status_counts[st] = visa_status_counts.get(st, 0) + 1

        # 5. Attention Required items
        attention = []
        if unassigned_count > 0:
            attention.append(f"{unassigned_count} lead(s) created on {target_date} require counselor assignment ({backlog_rate} unassigned backlog).")
        if len(overdue_followups) > 0:
            attention.append(f"{len(overdue_followups)} overdue follow-up task(s) require counselor attention.")
        if len(open_followups) > 0:
            attention.append(f"{len(open_followups)} open follow-up task(s) active in CRM.")

        return {
            "success": True,
            "date": target_date,
            "summary_title": f"Executive CRM Management Summary for {target_date}",
            "leads": {
                "total": total_leads,
                "by_department": dept_counts,
                "by_source": source_counts,
                "by_status": status_counts,
            },
            "assignment": {
                "assigned": assigned_count,
                "unassigned": unassigned_count,
                "backlog_rate": backlog_rate,
                "counselor_distribution": counselor_counts,
                "unassigned_lead_ids": [l.get("name") for l in unassigned_list[:10]],
            },
            "followups": {
                "total": len(followups_list),
                "open_count": len(open_followups),
                "overdue_count": len(overdue_followups),
                "backlog": len(open_followups),
                "sample": followups_list[:5],
            },
            "tasks": {
                "total": len(tasks_list),
                "open_count": len(open_tasks),
                "sample": tasks_list[:5],
            },
            "visa_applications": {
                "month_to_date_total": len(visas_list),
                "by_status": visa_status_counts,
                "sample": visas_list[:5],
            },
            "attention_required": attention,
        }


frappe_client = FrappeClient()
