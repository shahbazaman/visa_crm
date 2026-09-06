"""
Controlled MCP Reporting Tools for Frappe CRM.
Exposes read-only reporting capabilities with strict schema boundaries and error handling.
"""

from typing import Any, Dict, Optional
from frappe_client import frappe_client, FrappeClientError


async def get_leads_by_date(date: str) -> Dict[str, Any]:
    """
    Returns CRM leads created on a specific calendar date from Frappe CRM.

    Args:
        date (str): Calendar date strictly in YYYY-MM-DD format (e.g. '2026-09-06').

    Returns:
        dict: Structured result containing:
            - success (bool): True if retrieval succeeded.
            - date (str): The requested date.
            - total (int): Count of leads created on this date.
            - leads (list): Array of lead records.
    """
    try:
        return await frappe_client.get_leads_by_date(date)
    except FrappeClientError as exc:
        return {"success": False, "error": str(exc)}
    except Exception:
        return {"success": False, "error": "Failed to fetch leads for the specified date."}


async def get_lead_report(start_date: str, end_date: str) -> Dict[str, Any]:
    """
    Returns an aggregated CRM lead report for a specified date range.
    Includes totals, breakdown by department, breakdown by source, breakdown by status,
    and assigned vs unassigned distribution.

    Args:
        start_date (str): Start date in YYYY-MM-DD format.
        end_date (str): End date in YYYY-MM-DD format.

    Returns:
        dict: Structured report containing:
            - success (bool): True if succeeded.
            - start_date (str): Validated start date.
            - end_date (str): Validated end date.
            - total_leads (int): Total lead count in the period.
            - leads_by_department (dict): Mapping of department names to lead counts.
            - leads_by_source (dict): Mapping of lead sources (e.g. Meta Instant Form) to counts.
            - leads_by_status (dict): Mapping of statuses (e.g. Qualified, Open) to counts.
            - assigned_vs_unassigned (dict): Counts of assigned and unassigned leads.
            - leads (list): Controlled lead records.
    """
    try:
        return await frappe_client.get_lead_report(start_date, end_date)
    except FrappeClientError as exc:
        return {"success": False, "error": str(exc)}
    except Exception:
        return {"success": False, "error": "Failed to generate lead report."}


async def get_leads_by_department(department: str) -> Dict[str, Any]:
    """
    Returns CRM leads belonging to a specific department (e.g. 'Holidays - MEH', 'Global visa - MEH').

    Args:
        department (str): Department name or search string (e.g. 'Holidays - MEH', 'Global visa', 'Holidays').

    Returns:
        dict: Structured result containing:
            - success (bool): True if succeeded.
            - department (str): The query department.
            - total (int): Total leads found.
            - leads (list): Array of matching lead records.
    """
    try:
        return await frappe_client.get_leads_by_department(department)
    except FrappeClientError as exc:
        return {"success": False, "error": str(exc)}
    except Exception:
        return {"success": False, "error": "Failed to fetch leads for the specified department."}


async def get_leads_by_counselor(counselor: str) -> Dict[str, Any]:
    """
    Returns CRM leads assigned to a specific counselor or employee user.

    Args:
        counselor (str): Counselor username, email, or name identifier.

    Returns:
        dict: Structured result containing:
            - success (bool): True if succeeded.
            - counselor (str): The counselor queried.
            - total (int): Total assigned leads found.
            - leads (list): Array of lead records.
    """
    try:
        return await frappe_client.get_leads_by_counselor(counselor)
    except FrappeClientError as exc:
        return {"success": False, "error": str(exc)}
    except Exception:
        return {"success": False, "error": "Failed to fetch leads for the specified counselor."}


async def get_lead_sources(
    start_date: Optional[str] = None, end_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Returns lead counts aggregated by acquisition source (e.g. Meta Instant Form, WhatsApp, Meta Ads, Website).

    Args:
        start_date (str, optional): Start date in YYYY-MM-DD format.
        end_date (str, optional): End date in YYYY-MM-DD format.

    Returns:
        dict: Structured result containing:
            - success (bool): True if succeeded.
            - start_date (str or None): Start date filter.
            - end_date (str or None): End date filter.
            - total (int): Total leads evaluated.
            - sources (dict): Mapping of actual production sources to lead counts.
    """
    try:
        return await frappe_client.get_lead_sources(start_date, end_date)
    except FrappeClientError as exc:
        return {"success": False, "error": str(exc)}
    except Exception:
        return {"success": False, "error": "Failed to aggregate lead sources."}


async def get_unassigned_leads(
    start_date: Optional[str] = None, end_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Returns CRM leads where counselor/owner assignment is currently missing or pending.

    Args:
        start_date (str, optional): Start date in YYYY-MM-DD format.
        end_date (str, optional): End date in YYYY-MM-DD format.

    Returns:
        dict: Structured result containing:
            - success (bool): True if succeeded.
            - start_date (str or None): Start date filter.
            - end_date (str or None): End date filter.
            - total (int): Number of unassigned leads.
            - unassigned_leads (list): Array of unassigned lead records.
    """
    try:
        return await frappe_client.get_unassigned_leads(start_date, end_date)
    except FrappeClientError as exc:
        return {"success": False, "error": str(exc)}
    except Exception:
        return {"success": False, "error": "Failed to fetch unassigned leads."}


async def get_followups(
    start_date: Optional[str] = None, end_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Returns controlled follow-up and reminder records linked to CRM leads.

    Args:
        start_date (str, optional): Start date in YYYY-MM-DD format.
        end_date (str, optional): End date in YYYY-MM-DD format.

    Returns:
        dict: Structured result containing:
            - success (bool): True if succeeded.
            - total (int): Total follow-ups found.
            - followups (list): Array of follow-up items with due dates, descriptions, and linked records.
    """
    try:
        return await frappe_client.get_followups(start_date, end_date)
    except FrappeClientError as exc:
        return {"success": False, "error": str(exc)}
    except Exception:
        return {"success": False, "error": "Failed to fetch follow-ups."}


async def get_tasks(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    assigned_employee: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Returns controlled task records linked to CRM leads or employees.

    Args:
        start_date (str, optional): Start date in YYYY-MM-DD format.
        end_date (str, optional): End date in YYYY-MM-DD format.
        assigned_employee (str, optional): User or employee identifier to filter tasks.

    Returns:
        dict: Structured result containing:
            - success (bool): True if succeeded.
            - total (int): Total tasks found.
            - tasks (list): Array of tasks with task_name, subject, due_date, status, and linked CRM record.
    """
    try:
        return await frappe_client.get_tasks(start_date, end_date, assigned_employee)
    except FrappeClientError as exc:
        return {"success": False, "error": str(exc)}
    except Exception:
        return {"success": False, "error": "Failed to fetch tasks."}


async def get_visa_applications(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Returns controlled Visa Application reporting records from Frappe CRM.

    Args:
        start_date (str, optional): Start date in YYYY-MM-DD format.
        end_date (str, optional): End date in YYYY-MM-DD format.
        status (str, optional): Visa application status (e.g. 'Draft', 'Submitted', 'Approved', 'Rejected').

    Returns:
        dict: Structured result containing:
            - success (bool): True if succeeded.
            - total (int): Total applications found.
            - visa_applications (list): Array of visa application records with applicant name, visa type, country, and status.
    """
    try:
        return await frappe_client.get_visa_applications(start_date, end_date, status)
    except FrappeClientError as exc:
        return {"success": False, "error": str(exc)}
    except Exception:
        return {"success": False, "error": "Failed to fetch visa applications."}
