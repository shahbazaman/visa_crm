"""
Controlled MCP Reporting Tools for Frappe CRM.
Exposes read-only reporting capabilities with rich business intelligence semantics,
date handling, and multi-tool reasoning guidance for Google Gemini.
"""

from typing import Any, Dict, Optional
from frappe_client import frappe_client, FrappeClientError


async def get_leads_by_date(date: str) -> Dict[str, Any]:
    """
    Returns CRM leads created on a specific calendar date from Frappe CRM.

    Business Context:
        Use this tool when the user asks for leads on a specific day (e.g. 'Show leads from yesterday',
        'Leads on September 5, 2026', 'What leads arrived on 2026-09-06?').

    Date Semantics:
        - Must be formatted as an ISO date string: YYYY-MM-DD.
        - Interpreted in the Frappe CRM production timezone (Asia/Dubai, UTC+4).
        - For 'yesterday', calculate the calendar day before today in YYYY-MM-DD.
        - For 'today', you may also use 'get_today_leads'.

    When NOT to use:
        - Do NOT use for date ranges spanning multiple days (use 'get_lead_report' instead).
        - Do NOT use for department-specific filtering across all time (use 'get_leads_by_department').

    Args:
        date (str): Calendar day strictly in YYYY-MM-DD format (e.g. '2026-09-06').

    Returns:
        dict: Structured payload with 'success', 'date', 'total', and 'leads' list containing
              name, customer_name, email, phone, status, source, department, assigned_counselor, creation.
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
    Includes totals, department breakdown, source breakdown, status breakdown,
    and assigned vs unassigned distributions.

    Business Context:
        Use this tool when the user asks broad reporting, trend, or volume questions across a period, such as:
        - 'Give me a sales report for this week'
        - 'How many leads did each department receive this month?'
        - 'What is the lead breakdown for the first week of September?'
        - 'Which department received the most leads this week?'

    Date Semantics:
        - start_date and end_date must be strictly YYYY-MM-DD.
        - start_date must be less than or equal to end_date.
        - For 'this week', supply Monday through Sunday (or start of week to today) in YYYY-MM-DD.
        - For 'this month', supply YYYY-MM-01 through today in YYYY-MM-DD.

    When NOT to use:
        - Do NOT use when the user only wants follow-ups or tasks (use 'get_followups' or 'get_tasks').
        - Do NOT use when looking for a single specific counselor's assigned leads (use 'get_leads_by_counselor').

    Args:
        start_date (str): Beginning of date range (YYYY-MM-DD).
        end_date (str): End of date range (YYYY-MM-DD).

    Returns:
        dict: Aggregated report containing total_leads, leads_by_department, leads_by_source,
              leads_by_status, assigned_vs_unassigned counts, and lead records.
    """
    try:
        return await frappe_client.get_lead_report(start_date, end_date)
    except FrappeClientError as exc:
        return {"success": False, "error": str(exc)}
    except Exception:
        return {"success": False, "error": "Failed to generate lead report."}


async def get_leads_by_department(department: str) -> Dict[str, Any]:
    """
    Returns CRM leads belonging to a specific department in Frappe CRM.

    Business Context:
        Use this tool when the user asks about department-specific leads, e.g.:
        - 'Show me leads for Holidays'
        - 'How many leads does Global visa have?'
        - 'List all leads belonging to Holidays - MEH'

    Production Department Values:
        - 'Holidays - MEH' (or simply 'Holidays')
        - 'Global visa - MEH' (or simply 'Global visa')
        - Fuzzy matching is supported (e.g. 'Holidays' matches 'Holidays - MEH').

    When NOT to use:
        - Do NOT use for cross-department comparative reports (use 'get_lead_report').

    Args:
        department (str): Department name or keyword (e.g. 'Holidays - MEH', 'Global visa').

    Returns:
        dict: Payload with 'success', 'department', 'total', and 'leads'.
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

    Business Context:
        Use this tool when the user asks about an individual counselor's assigned leads, e.g.:
        - 'Show leads assigned to Administrator'
        - 'How many leads does counselor Akhil have?'
        - 'Which leads are assigned to admin@middleeast.com?'

    Matching Semantics:
        - Matches against the production CRM lead owner / counselor field.
        - Supports email, username, or partial name.

    When NOT to use:
        - Do NOT use when looking for unassigned leads (use 'get_unassigned_leads').

    Args:
        counselor (str): Counselor username, email, or identifier.

    Returns:
        dict: Payload with 'success', 'counselor', 'total', and 'leads'.
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
    Returns lead acquisition counts aggregated by source channel.

    Business Context:
        Use this tool when the user asks about lead sources, marketing channels, or ad platforms:
        - 'How many leads came from Meta this month?'
        - 'What sources are bringing in leads?'
        - 'Show today's Meta leads'
        - 'How many leads came from WhatsApp vs Website?'

    Production Sources:
        - 'Meta Instant Form', 'Meta Ads', 'WhatsApp', 'Website', 'Facebook', 'Manual', 'Cold Calling'.

    Args:
        start_date (str, optional): Range start date in YYYY-MM-DD format.
        end_date (str, optional): Range end date in YYYY-MM-DD format.

    Returns:
        dict: Payload with 'sources' mapping each source name to its count, plus 'total'.
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

    Business Context:
        Use this tool when the user asks about unassigned leads, unattended backlog, or assignment queues:
        - 'Show me unassigned leads'
        - 'How many leads need counselor assignment today?'
        - 'Which leads are not yet assigned to any counselor?'

    Assignment Semantics:
        - Identifies leads where 'assignment_status' is 'Unassigned' or 'Needs Assignment',
          or where 'lead_owner' is empty, None, or unassigned default ('Administrator').

    Args:
        start_date (str, optional): Filter start date in YYYY-MM-DD format.
        end_date (str, optional): Filter end date in YYYY-MM-DD format.

    Returns:
        dict: Payload with 'unassigned_leads' array and 'total'.
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

    Business Context:
        Use this tool when the user asks about follow-ups, calls, or reminders:
        - 'Show today's follow-ups'
        - 'What follow-up calls are scheduled for this week?'
        - 'Are there pending follow-ups for our CRM leads?'

    Target Production Data:
        - Follow-up ToDo items linked to CRM Lead or Lead Intake Queue.
        - Provides description, due_date, status ('Open', 'Closed'), assigned_to, linked_crm_record.

    Args:
        start_date (str, optional): Filter start date in YYYY-MM-DD format.
        end_date (str, optional): Filter end date in YYYY-MM-DD format.

    Returns:
        dict: Payload with 'followups' list and 'total'.
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

    Business Context:
        Use this tool when the user asks about operational tasks or counselor to-do items:
        - 'Show today's tasks'
        - 'What tasks are assigned to employee X?'
        - 'Show open tasks for this week'

    Args:
        start_date (str, optional): Filter start date in YYYY-MM-DD format.
        end_date (str, optional): Filter end date in YYYY-MM-DD format.
        assigned_employee (str, optional): Filter tasks by assigned user or employee.

    Returns:
        dict: Payload with 'tasks' list containing task_name, subject, assigned_employee, due_date, status, linked_crm_record.
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
    Returns controlled Visa Application reporting data from Frappe CRM.

    Business Context:
        Use this tool when the user asks about visa applications, applicant statuses, or visa conversions:
        - 'How many visa applications were created this month?'
        - 'Show me visa applications in Draft status'
        - 'What visa applications are currently being processed?'

    Production Statuses:
        - 'Draft', 'Submitted', 'Approved', 'Rejected'.

    Args:
        start_date (str, optional): Filter start date in YYYY-MM-DD format.
        end_date (str, optional): Filter end date in YYYY-MM-DD format.
        status (str, optional): Filter by status (e.g. 'Draft', 'Approved').

    Returns:
        dict: Payload with 'visa_applications' list and 'total'.
    """
    try:
        return await frappe_client.get_visa_applications(start_date, end_date, status)
    except FrappeClientError as exc:
        return {"success": False, "error": str(exc)}
    except Exception:
        return {"success": False, "error": "Failed to fetch visa applications."}


async def get_management_summary(date: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns an aggregated executive management briefing combining lead volumes,
    department splits, counselor assignment health, active follow-ups, visa conversions,
    and items requiring immediate managerial attention.

    Business Context:
        Use this tool for broad executive questions, such as:
        - 'Give me a management summary for today'
        - 'What needs attention today?'
        - 'How is the CRM performing today?'
        - 'Provide an executive briefing on today\'s operations'

    Combines:
        1. Lead Volume & Department Breakdown (Holidays vs Global visa).
        2. Acquisition Channel Distributions (Meta, WhatsApp, Website).
        3. Assignment Health (Assigned count vs Unassigned backlog).
        4. Follow-up & Task Pipeline (Open items due today).
        5. Visa Application Conversions (Month-to-date total).
        6. Attention Required Alerts (e.g. unassigned leads needing allocation).

    Args:
        date (str, optional): Calendar date in YYYY-MM-DD format. Defaults to today.

    Returns:
        dict: Comprehensive executive summary formatted for managerial review.
    """
    try:
        return await frappe_client.get_management_summary(date)
    except FrappeClientError as exc:
        return {"success": False, "error": str(exc)}
    except Exception:
        return {"success": False, "error": "Failed to generate management summary."}
