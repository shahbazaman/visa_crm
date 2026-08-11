#!/usr/bin/env python3
"""
STRANDED QUEUE RECOVERY SCRIPT — visa_crm Meta Lead Pipeline

Purpose:
  After refreshing the Meta access token, queues that hit max_attempts (5/5)
  on GRAPH_DOWNLOAD need their max_attempts bumped so they can retry again.

Usage (run via bench console or bench execute):
  bench --site <your-site> execute visa_crm.api.recovery.recover_failed_graph_queues --kwargs '{"dry_run": false}'

Or run directly:
  bench --site <your-site> console
  >>> import visa_crm.api.recovery as r
  >>> r.recover_failed_graph_queues(dry_run=False)

WARNING: Only run AFTER the Meta access token has been refreshed in tabMeta Settings.
"""
import frappe
from frappe.utils import now_datetime, add_to_date


@frappe.whitelist()
def recover_failed_graph_queues(dry_run=True, max_queues=500):
    """
    Reset GRAPH_DOWNLOAD stages that are FAILED (e.g. token expiry or permission errors)
    so they can retry with the refreshed token.

    Args:
        dry_run (bool): If True, report what would be done without making changes.
        max_queues (int): Safety limit on number of queues to process.

    Returns:
        dict with counts of recovered, skipped, total_found
    """
    now = now_datetime()
    retry_at = add_to_date(now, minutes=1)  # retry immediately

    # Find ALL GRAPH_DOWNLOAD stages that failed
    failed_stages = frappe.db.sql(
        """
        SELECT s.name as stage_name, s.queue, s.attempt_count, s.max_attempts,
               s.last_error, q.orchestration_status, q.source_lead_id
        FROM `tabLead Intake Stage` s
        JOIN `tabLead Intake Queue` q ON q.name = s.queue
        WHERE s.stage = 'GRAPH_DOWNLOAD'
          AND s.state = 'FAILED'
        ORDER BY q.creation ASC
        LIMIT %s
        """,
        (max_queues,),
        as_dict=True,
    )

    print(f"Found {len(failed_stages)} GRAPH_DOWNLOAD stages in FAILED state")
    if dry_run:
        print("DRY RUN — no changes made")
        for s in failed_stages[:20]:
            print(f"  Would recover: {s.queue} | attempt {s.attempt_count}/{s.max_attempts} | {s.source_lead_id} | error: {str(s.last_error)[:60]}")
        if len(failed_stages) > 20:
            print(f"  ... and {len(failed_stages)-20} more")
        return {"dry_run": True, "would_recover": len(failed_stages)}

    recovered = 0
    for s in failed_stages:
        try:
            # Bump max_attempts so retry is possible, reset state to FAILED with next_retry_at now
            new_max = max(int(s.max_attempts or 5), int(s.attempt_count or 0)) + 1
            frappe.db.set_value(
                "Lead Intake Stage",
                s.stage_name,
                {
                    "state": "FAILED",
                    "max_attempts": new_max,
                    "next_retry_at": retry_at,
                    "lease_owner": None,
                    "lease_token": None,
                    "lease_expires_at": None,
                },
                update_modified=False,
            )
            # Update queue status to trigger re-pickup
            frappe.db.set_value(
                "Lead Intake Queue",
                s.queue,
                {
                    "status": "Needs Retry",
                    "next_action_at": retry_at,
                },
                update_modified=False,
            )
            recovered += 1
        except Exception as e:
            print(f"  ERROR on {s.queue}: {e}")

    if recovered:
        frappe.db.commit()
    print(f"Recovered {recovered}/{len(failed_stages)} queues for retry")
    return {"recovered": recovered, "total_found": len(failed_stages)}


@frappe.whitelist()
def recover_normalized_payload_missing_queues(dry_run=True, max_queues=200):
    """
    For queues where GRAPH_DOWNLOAD succeeded but downstream stages failed
    with 'Normalized payload is missing', reset those downstream stages
    so they can re-run after GRAPH_DOWNLOAD has valid data.

    These queues have:
    - GRAPH_DOWNLOAD: COMPLETED (graph_payload exists)
    - NORMALIZE/CUSTOMER360/etc: FAILED with 'Normalized payload is missing'
    """
    error_pattern = "Normalized payload is missing"
    now = now_datetime()
    retry_at = add_to_date(now, minutes=2)

    # Find queues where NORMALIZE/downstream is FAILED but GRAPH_DOWNLOAD is COMPLETED
    affected = frappe.db.sql(
        """
        SELECT DISTINCT s.queue
        FROM `tabLead Intake Stage` s
        WHERE s.stage IN ('NORMALIZE', 'CUSTOMER360', 'LEAD_WORKFLOW',
                          'VISA_APPLICATION', 'COMMUNICATION_EVENT', 'FOLLOW_UP',
                          'COUNSELOR_ASSIGNMENT')
          AND s.state = 'FAILED'
          AND s.last_error LIKE %s
          AND EXISTS (
            SELECT 1 FROM `tabLead Intake Stage` s2
            WHERE s2.queue = s.queue
              AND s2.stage = 'GRAPH_DOWNLOAD'
              AND s2.state = 'COMPLETED'
          )
        LIMIT %s
        """,
        (f"%{error_pattern}%", max_queues),
        as_dict=True,
    )

    queues = [r.queue for r in affected]
    print(f"Found {len(queues)} queues with 'Normalized payload missing' but Graph completed")

    if dry_run:
        print("DRY RUN — no changes made")
        for q in queues[:10]:
            print(f"  Would reset downstream stages for: {q}")
        return {"dry_run": True, "would_recover": len(queues)}

    recovered = 0
    stages_to_reset = (
        "NORMALIZE", "CLASSIFICATION", "CUSTOMER360", "CRM_LEAD",
        "LEAD_WORKFLOW", "VISA_APPLICATION", "COMMUNICATION_EVENT",
        "FOLLOW_UP", "COUNSELOR_ASSIGNMENT",
    )
    for queue_name in queues:
        try:
            for stage in stages_to_reset:
                stage_id = f"{queue_name}:{stage}"
                if frappe.db.exists("Lead Intake Stage", stage_id):
                    current = frappe.db.get_value(
                        "Lead Intake Stage", stage_id, ["state", "max_attempts", "attempt_count"], as_dict=True
                    )
                    if current and current.state == "FAILED":
                        new_max = max(int(current.max_attempts or 5), int(current.attempt_count or 0)) + 1
                        frappe.db.set_value(
                            "Lead Intake Stage",
                            stage_id,
                            {
                                "state": "FAILED",
                                "max_attempts": new_max,
                                "next_retry_at": retry_at,
                                "lease_owner": None,
                                "lease_token": None,
                                "lease_expires_at": None,
                            },
                            update_modified=False,
                        )
            frappe.db.set_value(
                "Lead Intake Queue",
                queue_name,
                {"status": "Needs Retry", "next_action_at": retry_at},
                update_modified=False,
            )
            recovered += 1
        except Exception as e:
            print(f"  ERROR on {queue_name}: {e}")

    if recovered:
        frappe.db.commit()
    print(f"Reset downstream stages for {recovered}/{len(queues)} queues")
    return {"recovered": recovered, "total_found": len(queues)}


@frappe.whitelist()
def recover_graph_queues_dry_run():
    """System Console friendly dry-run wrapper without kwargs."""
    return recover_failed_graph_queues(dry_run=True)


@frappe.whitelist()
def recover_graph_queues_execute():
    """System Console friendly live recovery execution wrapper without kwargs."""
    return recover_failed_graph_queues(dry_run=False)


@frappe.whitelist()
def retry_queue(queue_name):
    """
    Safely reset the failed stage of a single Lead Intake Queue record
    and process it synchronously through the pipeline engine.

    Permission: Requires System Manager role.
    """
    if "System Manager" not in frappe.get_roles():
        frappe.throw("System Manager role required", frappe.PermissionError)

    if not frappe.db.exists("Lead Intake Queue", queue_name):
        frappe.throw(f"Lead Intake Queue {queue_name} not found")

    from visa_crm.api.pipeline_engine import stages_for, retry_stage, ensure_stage_ledger
    from visa_crm.api.intake_processor import process_queue

    ensure_stage_ledger(queue_name)
    stages = stages_for(queue_name)
    queue = frappe.get_doc("Lead Intake Queue", queue_name)
    c_name = frappe.db.get_value("Customer", queue.matched_customer, "customer_name") if queue.matched_customer else None
    l_name = frappe.db.get_value("CRM Lead", queue.matched_lead, "lead_name") if queue.matched_lead else None
    placeholder = bool((c_name and c_name.startswith("Meta Lead ")) or (l_name and l_name.startswith("Meta Lead ")))

    failed_stages = [s.stage for s in stages if s.state == "FAILED"]
    if placeholder:
        for stg in ("CUSTOMER360", "CRM_LEAD"):
            if stg not in failed_stages:
                failed_stages.append(stg)

    for stg in failed_stages:
        retry_stage(queue_name, stg, force=True)

    result = process_queue(queue_name)
    frappe.db.commit()

    updated = frappe.get_doc("Lead Intake Queue", queue_name)
    return {
        "ok": result.get("ok", False),
        "queue": queue_name,
        "status": updated.status,
        "current_stage": updated.current_stage,
        "orchestration_status": updated.orchestration_status,
        "matched_customer": getattr(updated, "matched_customer", None),
        "matched_lead": getattr(updated, "matched_lead", None),
        "visa_application": getattr(updated, "visa_application", None),
        "communication_event": getattr(updated, "communication_event", None),
        "last_error": getattr(updated, "last_error", None),
        "result": result
    }


@frappe.whitelist()
def verify_queue(queue_name):
    """
    Read-only diagnostic function to inspect the full pipeline state,
    data contracts, stage ledger, Customer, CRM Lead, and downstream records
    for a given Lead Intake Queue without mutating any database state.
    """
    if "System Manager" not in frappe.get_roles():
        frappe.throw("System Manager role required", frappe.PermissionError)

    if not frappe.db.exists("Lead Intake Queue", queue_name):
        frappe.throw(f"Lead Intake Queue {queue_name} not found")

    queue = frappe.get_doc("Lead Intake Queue", queue_name)

    stages = frappe.get_all(
        "Lead Intake Stage",
        filters={"queue": queue_name},
        fields=[
            "stage", "sequence", "requirement_class", "state",
            "attempt_count", "max_attempts", "next_retry_at",
            "last_error_class", "last_error", "result_doctype",
            "result_name", "warning", "skip_reason", "result_json"
        ],
        order_by="sequence asc"
    )

    customer = None
    if queue.get("matched_customer") and frappe.db.exists("Customer", queue.matched_customer):
        c_doc = frappe.get_doc("Customer", queue.matched_customer)
        customer = {
            "name": c_doc.name,
            "customer_name": c_doc.customer_name,
            "mobile_no": c_doc.get("mobile_no"),
            "email_id": c_doc.get("email_id"),
            "crm_lead": c_doc.get("crm_lead")
        }

    crm_lead = None
    if queue.get("matched_lead") and frappe.db.exists("CRM Lead", queue.matched_lead):
        l_doc = frappe.get_doc("CRM Lead", queue.matched_lead)
        crm_lead = {
            "name": l_doc.name,
            "lead_name": l_doc.lead_name,
            "mobile_no": l_doc.get("mobile_no"),
            "email": l_doc.get("email"),
            "facebook_lead_id": l_doc.get("facebook_lead_id"),
            "meta_campaign_name": l_doc.get("meta_campaign_name"),
            "meta_ad_name": l_doc.get("meta_ad_name"),
            "meta_adset_name": l_doc.get("meta_adset_name"),
            "meta_ad_id": l_doc.get("meta_ad_id"),
            "facebook_form_id": l_doc.get("facebook_form_id"),
            "page_id": l_doc.get("page_id"),
            "customer360": l_doc.get("customer360") or l_doc.get("customer_360")
        }

    norm_stage_row = next((s for s in stages if s.stage == "NORMALIZE"), None)

    return {
        "queue": {
            "name": queue.name,
            "status": queue.status,
            "orchestration_status": queue.orchestration_status,
            "current_stage": queue.current_stage,
            "source_lead_id": queue.source_lead_id,
            "matched_customer": queue.get("matched_customer"),
            "matched_lead": queue.get("matched_lead"),
            "visa_application": queue.get("visa_application"),
            "communication_event": queue.get("communication_event"),
            "followup_reference": queue.get("followup_reference"),
            "assigned_employee": queue.get("assigned_employee"),
            "ai_status": queue.get("ai_status"),
            "normalized_payload": queue.get("normalized_payload")
        },
        "customer": customer,
        "crm_lead": crm_lead,
        "stages": stages,
        "normalization_check": {
            "normalize_stage_state": norm_stage_row.state if norm_stage_row else None,
            "normalize_stage_result_json": norm_stage_row.result_json if norm_stage_row else None
        }
    }

if __name__ == "__main__":
    print("This script must be run via bench console or bench execute.")
    print("Usage:")
    print("  bench --site <site> execute visa_crm.api.recovery.recover_failed_graph_queues --kwargs '{\"dry_run\": false}'")
