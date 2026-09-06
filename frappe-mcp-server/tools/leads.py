"""
MCP Tool: get_today_leads
Exposes read-only access to today's CRM Lead records from production Frappe CRM.
"""

from typing import Any, Dict
from frappe_client import frappe_client, FrappeClientError


async def get_today_leads() -> Dict[str, Any]:
    """
    Returns today's CRM Lead records from the production Visa CRM Frappe instance. This is a read-only reporting tool.

    Returns:
        dict: A structured dictionary containing:
            - success (bool): True if retrieval succeeded.
            - date (str): Query date in YYYY-MM-DD format.
            - total (int): Total number of leads created today.
            - leads (list): Array of lead records with fields:
                - name (str): Lead ID (e.g. CRM-LEAD-2026-00629)
                - customer_name (str): Full customer name
                - email (str or None): Contact email
                - phone (str or None): Contact phone number
                - status (str or None): Current lead status (e.g. Qualified, Open)
                - source (str or None): Lead origin (e.g. Meta Instant Form)
                - creation (str): Creation timestamp
                - assigned_counselor (str or None): Assigned employee/counselor
                - department (str or None): Business department
    """
    try:
        return await frappe_client.get_today_leads()
    except FrappeClientError as exc:
        return {
            "success": False,
            "error": str(exc),
        }
    except Exception:
        return {
            "success": False,
            "error": "Frappe CRM is currently unavailable.",
        }
