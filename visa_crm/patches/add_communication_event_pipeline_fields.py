"""
Patch: add_communication_event_pipeline_fields
==============================================
Safe, idempotent, deterministic schema migration & deduplication for Communication Event:
1. Syncs Communication Event DocType definition from JSON fixture.
2. Adds missing physical columns to MariaDB tabCommunication Event table.
3. Normalizes empty strings (event_id = '') to NULL.
4. Backfills namespaced event_id ('meta:lead:{id}') on canonical records first.
5. Reconciles duplicate Communication Events:
   - Selects canonical record (earliest creation, lowest name).
   - Merges field data into canonical record without overwriting valid data.
   - Rewrites references across all linked DocTypes + ToDo dynamic links.
   - Deletes duplicate records safely.
6. Applies UNIQUE INDEX (event_id) only after zero duplicates remain.
"""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Communication Event"):
        return

    # 1. Sync DocType definition from JSON fixture
    frappe.reload_doctype("Communication Event", force=True)
    frappe.db.commit()

    table = "tabCommunication Event"

    # 2. Add missing columns using ADD COLUMN IF NOT EXISTS
    columns_to_add = [
        ("event_id", "varchar(140) DEFAULT NULL"),
        ("source_channel", "varchar(140) DEFAULT NULL"),
        ("conversation_id", "varchar(140) DEFAULT NULL"),
        ("customer360", "varchar(140) DEFAULT NULL"),
        ("visa_application", "varchar(140) DEFAULT NULL"),
        ("lead_intake_queue", "varchar(140) DEFAULT NULL"),
        ("followup_reference", "varchar(140) DEFAULT NULL"),
        ("meta_campaign_name", "varchar(140) DEFAULT NULL"),
        ("meta_campaign_id", "varchar(140) DEFAULT NULL"),
        ("meta_adset_name", "varchar(140) DEFAULT NULL"),
        ("meta_adset_id", "varchar(140) DEFAULT NULL"),
        ("meta_ad_name", "varchar(140) DEFAULT NULL"),
        ("meta_ad_id", "varchar(140) DEFAULT NULL"),
        ("facebook_page_id", "varchar(140) DEFAULT NULL"),
        ("facebook_form_id", "varchar(140) DEFAULT NULL"),
        ("facebook_lead_id", "varchar(140) DEFAULT NULL"),
        ("original_normalized_payload", "longtext DEFAULT NULL"),
        ("meta_attribution_json", "longtext DEFAULT NULL"),
        ("processing_timeline", "longtext DEFAULT NULL"),
    ]

    for col_name, col_def in columns_to_add:
        try:
            frappe.db.sql(f"ALTER TABLE `{table}` ADD COLUMN IF NOT EXISTS `{col_name}` {col_def}")
        except Exception as exc:
            print(f"  Note on ADD COLUMN {col_name}: {exc}")
    frappe.db.commit()

    # Normalize empty strings to NULL
    frappe.db.sql(f"UPDATE `{table}` SET event_id = NULL WHERE event_id = '' OR event_id = 'None'")
    frappe.db.commit()

    # Normalize legacy 'meta:{id}' format to 'meta:lead:{id}'
    frappe.db.sql(f"""
        UPDATE `{table}`
        SET event_id = CONCAT('meta:lead:', SUBSTRING(event_id, 6))
        WHERE event_id LIKE 'meta:%' AND event_id NOT LIKE 'meta:lead:%'
    """)
    frappe.db.commit()

    # 3. Deduplicate and Backfill by facebook_lead_id or lead_intake_queue
    lead_groups = frappe.db.sql(f"""
        SELECT facebook_lead_id, COUNT(*) as cnt
        FROM `{table}`
        WHERE facebook_lead_id IS NOT NULL AND facebook_lead_id != ''
        GROUP BY facebook_lead_id
        HAVING cnt > 1
    """, as_dict=True)

    linking_doctypes = [
        ("Counselor Assignment History", "communication_event"),
        ("Employee Evaluation", "communication_event"),
        ("Lead Intake AI Job", "communication_event"),
        ("Lead Assignment", "communication_event"),
        ("Call Intelligence", "communication_event"),
        ("Lead Intake Queue", "communication_event"),
        ("Communication Timeline Item", "communication_event"),
        ("Meta Webhook Event", "communication_event"),
        ("Lead Timeline", "communication_event"),
    ]

    for group in lead_groups:
        records = frappe.get_all(
            "Communication Event",
            filters={"facebook_lead_id": group.facebook_lead_id},
            fields=["*"],
            order_by="creation asc, name asc"
        )
        if len(records) > 1:
            canonical = records[0]
            canonical_name = canonical.name
            dup_records = records[1:]
            dup_names = [r.name for r in dup_records]

            # Merge missing non-null field data into canonical record
            meta_fields = [f.fieldname for f in frappe.get_meta("Communication Event").fields if f.fieldname]
            updates = {}
            for d_rec in dup_records:
                for field in meta_fields:
                    if not canonical.get(field) and d_rec.get(field):
                        updates[field] = d_rec.get(field)
                        canonical[field] = d_rec.get(field)

            if updates:
                frappe.db.set_value("Communication Event", canonical_name, updates, update_modified=False)

            # Rewrite references in all linked DocTypes
            for dt, link_field in linking_doctypes:
                if frappe.db.exists("DocType", dt):
                    dt_table = f"tab{dt}"
                    for d_name in dup_names:
                        frappe.db.sql(
                            f"UPDATE `{dt_table}` SET `{link_field}` = %s WHERE `{link_field}` = %s",
                            (canonical_name, d_name)
                        )

            # Rewrite ToDo Dynamic Links
            if frappe.db.exists("DocType", "ToDo"):
                for d_name in dup_names:
                    frappe.db.sql(
                        "UPDATE `tabToDo` SET reference_name = %s WHERE reference_type = 'Communication Event' AND reference_name = %s",
                        (canonical_name, d_name)
                    )

            # Delete duplicate rows
            for d_name in dup_names:
                frappe.db.sql(f"DELETE FROM `{table}` WHERE name = %s", (d_name,))

    frappe.db.commit()

    # 4. Backfill event_id for remaining single canonical records
    frappe.db.sql(f"""
        UPDATE `{table}`
        SET event_id = CONCAT('meta:lead:', facebook_lead_id)
        WHERE (event_id IS NULL OR event_id = '')
          AND facebook_lead_id IS NOT NULL AND facebook_lead_id != ''
    """)

    if frappe.db.exists("DocType", "Lead Intake Queue"):
        frappe.db.sql(f"""
            UPDATE `{table}` c
            JOIN `tabLead Intake Queue` q ON c.lead_intake_queue = q.name
            SET c.event_id = CONCAT('meta:lead:', q.source_lead_id)
            WHERE (c.event_id IS NULL OR c.event_id = '')
              AND q.source_lead_id IS NOT NULL AND q.source_lead_id != ''
        """)
    frappe.db.commit()

    # 5. Deduplicate by event_id if any remain
    event_groups = frappe.db.sql(f"""
        SELECT event_id, COUNT(*) as cnt
        FROM `{table}`
        WHERE event_id IS NOT NULL AND event_id != ''
        GROUP BY event_id
        HAVING cnt > 1
    """, as_dict=True)

    for dup in event_groups:
        records = frappe.get_all(
            "Communication Event",
            filters={"event_id": dup.event_id},
            fields=["*"],
            order_by="creation asc, name asc"
        )
        if len(records) > 1:
            canonical = records[0]
            canonical_name = canonical.name
            dup_records = records[1:]
            dup_names = [r.name for r in dup_records]

            for dt, link_field in linking_doctypes:
                if frappe.db.exists("DocType", dt):
                    dt_table = f"tab{dt}"
                    for d_name in dup_names:
                        frappe.db.sql(
                            f"UPDATE `{dt_table}` SET `{link_field}` = %s WHERE `{link_field}` = %s",
                            (canonical_name, d_name)
                        )

            if frappe.db.exists("DocType", "ToDo"):
                for d_name in dup_names:
                    frappe.db.sql(
                        "UPDATE `tabToDo` SET reference_name = %s WHERE reference_type = 'Communication Event' AND reference_name = %s",
                        (canonical_name, d_name)
                    )

            for d_name in dup_names:
                frappe.db.sql(f"DELETE FROM `{table}` WHERE name = %s", (d_name,))

    frappe.db.commit()

    # 6. Apply UNIQUE INDEX on event_id safely
    unique_idx = frappe.db.sql(
        f"SHOW INDEX FROM `{table}` WHERE Column_name = 'event_id' AND Non_unique = 0", as_dict=True
    )
    if not unique_idx:
        frappe.db.sql(f"ALTER TABLE `{table}` ADD UNIQUE INDEX `unique_event_id` (`event_id`)")
    frappe.db.commit()

    print(f"Communication Event migration & deduplication completed successfully. Unique index verified.")
