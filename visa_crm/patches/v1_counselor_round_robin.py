"""
visa_crm/patches/v1_counselor_round_robin.py
==============================================
Idempotent migration patch for V1 Counselor Round-Robin feature.

Runs:
1. Ensures ``Department Round Robin State`` DocType table exists.
2. Adds new columns to ``Counselor Assignment History`` if missing.
3. Ensures round-robin state rows exist for ``Holidays`` and ``Global Visa``.
"""

import frappe


def execute():
    _ensure_department_round_robin_state()
    _add_counselor_history_fields()
    frappe.db.commit()


def _ensure_department_round_robin_state():
    """Create the Department Round Robin State table if it doesn't exist."""
    if not frappe.db.table_exists("tabDepartment Round Robin State"):
        frappe.reload_doctype("Department Round Robin State")
        frappe.db.commit()

    # Seed rows for supported departments (idempotent)
    for dept in ("Holidays", "Global Visa"):
        if not frappe.db.exists("Department Round Robin State", dept):
            # Only create if the Department itself exists
            if frappe.db.exists("Department", dept) or True:  # allow pre-seeding
                frappe.db.sql(
                    """
                    INSERT IGNORE INTO `tabDepartment Round Robin State`
                    (name, department, current_index, creation, modified, modified_by, owner, docstatus)
                    VALUES (%s, %s, 0, NOW(), NOW(), 'Administrator', 'Administrator', 0)
                    """,
                    (dept, dept),
                )
    frappe.db.commit()


def _add_counselor_history_fields():
    """Add new V1 fields to Counselor Assignment History if they don't exist."""
    table = "tabCounselor Assignment History"
    if not frappe.db.table_exists(table):
        return

    columns_to_add = [
        ("assignment_type", "VARCHAR(100) DEFAULT NULL COMMENT 'Automatic Round Robin or Manual Override'"),
        ("previous_counselor", "VARCHAR(140) DEFAULT NULL"),
        ("override_reason", "TEXT DEFAULT NULL"),
        ("override_by", "VARCHAR(140) DEFAULT NULL"),
    ]

    existing_cols = {row[0] for row in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`")}

    for col, definition in columns_to_add:
        if col not in existing_cols:
            frappe.db.sql(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {definition}")
            frappe.db.commit()
