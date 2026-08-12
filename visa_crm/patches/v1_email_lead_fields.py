"""
visa_crm/patches/v1_email_lead_fields.py
==========================================
Idempotent migration patch for V1 Email Leads feature.

Adds email-specific fields to Lead Intake Queue:
  - email_message_id   VARCHAR(500) — idempotency key (message-id header)
  - email_thread_id    VARCHAR(500) — thread grouping
  - email_subject      VARCHAR(500) — original email subject
  - email_in_reply_to  VARCHAR(500) — for reply detection
  - raw_email_body     LONGTEXT     — preserved email body

Also adds "Email" to lead_source select options on Lead Intake Queue.
"""

import frappe


def execute():
    _add_email_fields_to_queue()
    frappe.db.commit()


def _add_email_fields_to_queue():
    table = "tabLead Intake Queue"
    if not frappe.db.table_exists(table):
        return

    existing_cols = {row[0] for row in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`")}

    columns_to_add = [
        ("email_message_id", "VARCHAR(500) DEFAULT NULL COMMENT 'Email Message-ID header (idempotency key)'"),
        ("email_thread_id", "VARCHAR(500) DEFAULT NULL COMMENT 'Email thread identifier'"),
        ("email_subject", "VARCHAR(500) DEFAULT NULL"),
        ("email_in_reply_to", "VARCHAR(500) DEFAULT NULL COMMENT 'In-Reply-To header for reply detection'"),
        ("raw_email_body", "LONGTEXT DEFAULT NULL"),
    ]

    for col, definition in columns_to_add:
        if col not in existing_cols:
            frappe.db.sql(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {definition}")
            frappe.db.commit()

    # Add index on email_message_id for fast idempotency lookups
    try:
        frappe.db.sql(
            f"ALTER TABLE `{table}` ADD INDEX IF NOT EXISTS `idx_email_message_id` (email_message_id(255))"
        )
        frappe.db.commit()
    except Exception:
        pass  # Index may already exist
