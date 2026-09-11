# -*- coding: utf-8 -*-
"""
Multi-Holiday Consolidation Engine for Visa CRM HR
===================================================
Seamlessly resolves multiple holiday lists per employee without modifying Frappe HR core.
Consolidates active assignments deterministically into an effective Employee Holiday List.
"""
import frappe
from frappe import _
from frappe.utils import getdate, today

def sync_employee_holidays(doc, method=None):
    """
    Called on Employee validate and on_update.
    Inspects custom_holiday_assignments and synthesizes an effective consolidated Holiday List.
    """
    # Check if employee has custom holiday assignments
    assignments = getattr(doc, "custom_holiday_assignments", None)
    if not assignments or len(assignments) == 0:
        return

    active_assignments = [a for a in assignments if a.is_active and a.holiday_list]
    if not active_assignments:
        return

    # Sort assignments by priority desc
    active_assignments.sort(key=lambda x: int(x.priority or 0), reverse=True)

    # Determine date span
    from_dates = [getdate(a.from_date) for a in active_assignments if a.from_date]
    to_dates = [getdate(a.to_date) for a in active_assignments if a.to_date]
    if not from_dates or not to_dates:
        return

    min_from = min(from_dates)
    max_to = max(to_dates)

    # Effective Holiday List Name: e.g. HL-HR-EMP-00001
    emp_id = doc.name or doc.employee or "NEW"
    consolidated_name = f"HL-{emp_id}"

    # Merge holidays from all lists
    holidays_by_date = {}

    for assign in reversed(active_assignments):  # lowest priority first so higher overwrites
        hl_doc = frappe.get_doc("Holiday List", assign.holiday_list)
        assign_from = getdate(assign.from_date) if assign.from_date else min_from
        assign_to = getdate(assign.to_date) if assign.to_date else max_to

        for h in hl_doc.holidays:
            h_date = getdate(h.holiday_date)
            if assign_from <= h_date <= assign_to:
                # Merge rule:
                # If existing is weekly_off (1) and current is not (0), festival takes precedence!
                current_is_festival = not bool(h.weekly_off)
                if h_date in holidays_by_date:
                    existing = holidays_by_date[h_date]
                    if current_is_festival:
                        holidays_by_date[h_date] = {
                            "holiday_date": str(h_date),
                            "description": h.description,
                            "weekly_off": 0
                        }
                    # else if current is weekly_off and existing is already festival, keep festival
                else:
                    holidays_by_date[h_date] = {
                        "holiday_date": str(h_date),
                        "description": h.description,
                        "weekly_off": 1 if h.weekly_off else 0
                    }

    # Ensure consolidated holiday list exists
    if frappe.db.exists("Holiday List", consolidated_name):
        consolidated_hl = frappe.get_doc("Holiday List", consolidated_name)
    else:
        consolidated_hl = frappe.new_doc("Holiday List")
        consolidated_hl.holiday_list_name = consolidated_name

    consolidated_hl.from_date = min_from
    consolidated_hl.to_date = max_to
    consolidated_hl.total_holidays = len(holidays_by_date)

    # Rebuild holidays child table
    consolidated_hl.set("holidays", [])
    for d in sorted(holidays_by_date.keys()):
        h_data = holidays_by_date[d]
        consolidated_hl.append("holidays", {
            "holiday_date": h_data["holiday_date"],
            "description": h_data["description"] or "Holiday",
            "weekly_off": h_data["weekly_off"]
        })

    consolidated_hl.flags.ignore_permissions = True
    consolidated_hl.save()

    # Point employee to consolidated list
    doc.holiday_list = consolidated_name
    if doc.name:
        frappe.db.set_value("Employee", doc.name, "holiday_list", consolidated_name)
