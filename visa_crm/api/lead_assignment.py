"""
visa_crm/api/lead_assignment.py
================================
Department-Aware Round-Robin Counselor Assignment + Manager Resolution + Override.

Routing Rules:
- Rule A (Holidays): Lead Category == "Holidays" -> Holidays department (e.g. Holidays - MEH / Holidays - HNC)
- Rule B (Global Visa): Lead Category == "Global Visa" -> Global Visa department (e.g. Global visa - MEH / Global Visa - HNC)
- Rule C (WhatsApp): Lead Source == "WhatsApp" -> Reservation department (e.g. Reservation - MEH / Reservation - HNC)
  Precedence: WhatsApp source routing takes precedence over Category routing.

Validation & Security Invariants:
- Counselors must be resolved from Active Employee records.
- Counselor's linked User must exist, be enabled, and NEVER be "Administrator" or a system placeholder.
- Counselors must belong to the exact target department (supporting company suffix variations).
- Counselor must have a valid Active Manager resolved via Employee.reports_to.
- Manager's linked User must exist, be enabled, and NEVER be "Administrator".
- If no eligible counselor or no valid manager exists, assignment fails cleanly without data loss.
- Never falls back to Administrator.
"""

import datetime
import json
import uuid

import frappe
from frappe.utils import getdate, now, now_datetime

from visa_crm.api.execution_history import record
from visa_crm.api.meta_utils import (
    has_doctype,
    has_field,
    load_json,
    log_info,
    meta_debug_log,
    safe_json_dumps,
    set_if_has,
)

# ---------------------------------------------------------------------------
# Public constants & department definitions
# ---------------------------------------------------------------------------

#: Department name prefixes that receive automatic round-robin assignment.
SUPPORTED_DEPARTMENT_PREFIXES = {"Holidays", "Global Visa", "Reservation"}
SUPPORTED_DEPARTMENTS = SUPPORTED_DEPARTMENT_PREFIXES

#: Users that must never be selected as a counselor or manager.
EXCLUDED_COUNSELOR_USERS = frozenset({"Administrator", "administrator", "Guest", "guest"})

#: How long (seconds) to hold the round-robin lock before expiry.
LOCK_TTL_SECONDS = 30


def is_supported_department(department):
    """Return True if department is supported for automatic round-robin assignment."""
    if not department:
        return False
    dept_lower = str(department).strip().lower()
    return any(
        dept_lower == p.lower() or dept_lower.startswith(p.lower() + " ") or dept_lower.startswith(p.lower() + "-")
        for p in SUPPORTED_DEPARTMENT_PREFIXES
    )


def is_whatsapp_lead(queue_doc=None, lead=None):
    """Return True if the lead originates from WhatsApp."""
    candidates = []
    if queue_doc:
        candidates.extend([
            getattr(queue_doc, "lead_source", None),
            getattr(queue_doc, "source", None),
            getattr(queue_doc, "source_channel", None),
            getattr(queue_doc, "event_type", None),
        ])
        raw = getattr(queue_doc, "raw_payload", None) or getattr(queue_doc, "normalized_payload", None)
        if raw:
            data = load_json(raw, {})
            if isinstance(data, dict):
                candidates.extend([
                    data.get("source"),
                    data.get("source_channel"),
                    data.get("lead_source"),
                    data.get("channel"),
                ])
    if lead and has_doctype("CRM Lead"):
        fields = [f for f in ("source", "lead_source") if has_field("CRM Lead", f)]
        if fields:
            lead_data = frappe.db.get_value("CRM Lead", lead, fields, as_dict=True) or {}
            candidates.extend(lead_data.values())

    for c in candidates:
        if c and "whatsapp" in str(c).strip().lower():
            return True
    return False


def resolve_canonical_department(dept_key):
    """
    Resolve the exact Department record name in the database for a department key.

    Checks in deterministic order:
    1. Production naming: e.g. 'Holidays - MEH', 'Global visa - MEH', 'Reservation - MEH'
    2. Local bench naming: e.g. 'Holidays - HNC', 'Global Visa - HNC', 'Reservation - HNC'
    3. Direct match: e.g. 'Holidays', 'Global Visa', 'Reservation'
    4. Category linked department if DocType Lead Category exists
    5. Case-insensitive prefix search in tabDepartment
    """
    if not dept_key or not has_doctype("Department"):
        return None

    dept_key_clean = str(dept_key).strip()

    # 1. Check exact known company department patterns
    for suffix in ("MEH", "HNC"):
        patterns = [
            f"{dept_key_clean} - {suffix}",
            f"{dept_key_clean.replace('Visa', 'visa')} - {suffix}",
            f"{dept_key_clean.replace('visa', 'Visa')} - {suffix}",
        ]
        for pat in patterns:
            if frappe.db.exists("Department", pat):
                return pat

    # 2. Check direct name
    if frappe.db.exists("Department", dept_key_clean):
        return dept_key_clean

    # 3. Check Lead Category linked department
    if has_doctype("Lead Category"):
        cat_dept = frappe.db.get_value("Lead Category", dept_key_clean, "department")
        if cat_dept and frappe.db.exists("Department", cat_dept):
            return cat_dept

    # 4. Prefix search
    candidates = frappe.get_all(
        "Department",
        filters={"name": ["like", f"{dept_key_clean}%"]},
        pluck="name",
        order_by="name asc",
    )
    if candidates:
        return candidates[0]

    return None


def get_responsible_department(queue_doc=None, lead=None):
    """
    Determine the responsible Department for counselor assignment using explicit business rules.

    Routing Precedence:
    1. Source == WhatsApp -> Reservation department (Reservation - MEH / Reservation - HNC)
    2. Category == "Holidays" -> Holidays department (Holidays - MEH / Holidays - HNC)
    3. Category == "Global Visa" -> Global Visa department (Global visa - MEH / Global Visa - HNC)
    4. Fall back to queue_doc.responsible_department or CRM Lead.responsible_department
    """
    # 1. Source Rule: WhatsApp takes highest precedence
    if is_whatsapp_lead(queue_doc=queue_doc, lead=lead):
        dept = resolve_canonical_department("Reservation")
        if dept:
            return dept

    # Extract Category
    category = None
    if queue_doc:
        category = getattr(queue_doc, "lead_category", None)
    if not category and lead and has_doctype("CRM Lead") and has_field("CRM Lead", "lead_category"):
        category = frappe.db.get_value("CRM Lead", lead, "lead_category")

    # 2. Category Rule: Holidays
    if category and str(category).strip().lower() == "holidays":
        dept = resolve_canonical_department("Holidays")
        if dept:
            return dept

    # 3. Category Rule: Global Visa
    if category and "global" in str(category).strip().lower() and "visa" in str(category).strip().lower():
        dept = resolve_canonical_department("Global Visa")
        if dept:
            return dept

    # 4. Fallback to explicitly recorded department on queue or lead
    if queue_doc:
        raw_dept = getattr(queue_doc, "responsible_department", None)
        if raw_dept and frappe.db.exists("Department", raw_dept):
            return raw_dept

    if lead and has_doctype("CRM Lead") and has_field("CRM Lead", "responsible_department"):
        lead_dept = frappe.db.get_value("CRM Lead", lead, "responsible_department")
        if lead_dept and frappe.db.exists("Department", lead_dept):
            return lead_dept

    return None


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------


def assign_lead(lead, queue_doc=None, strategy=None, context=None, communication_event=None):
    """
    Primary entry point called by the pipeline COUNSELOR_ASSIGNMENT stage.

    Returns the assigned Employee name, or ``None`` if no counselor/manager is available.
    Raises ``NotApplicable`` if the department is not supported.
    """
    context = context or {}
    meta_debug_log("counselor_assignment_start", lead=lead, **context)
    queue_name = getattr(queue_doc, "name", None)

    # 1. Idempotency guard — reuse existing assignment if present
    existing = _existing_assignment(queue_name)
    if existing:
        decision = {"strategy": "existing", "selected": existing}
        _record_success(queue_name, decision)
        meta_debug_log("counselor_assignment_end", lead=lead, employee=existing, **context)
        return existing

    # 2. Determine department using canonical business routing
    responsible_department = get_responsible_department(queue_doc, lead)

    # 3. Route by department support
    if not responsible_department or not is_supported_department(responsible_department):
        raise NotApplicable(
            f"Automatic counselor assignment is not configured for department: {responsible_department}"
        )

    # 4. Round-robin assignment for supported department
    employee, decision = _round_robin_assign(responsible_department, queue_doc)

    if not employee:
        log_info("meta_assignment_skipped", reason="no_employee", lead=lead, department=responsible_department)
        record(
            queue=queue_name,
            stage="COUNSELOR_ASSIGNMENT",
            execution_type="Stage",
            result="FAILED",
            failure_reason=f"No eligible counselor found for department: {responsible_department}",
            details=decision,
        )
        meta_debug_log("counselor_assignment_end", lead=lead, employee=None, **context)
        return None

    # 5. Resolve manager (counselor must have a valid active non-Administrator manager)
    manager_emp, manager_user = _resolve_manager(employee)
    if not manager_emp or not manager_user:
        log_info(
            "counselor_assignment_failed_no_manager",
            lead=lead,
            employee=employee,
            department=responsible_department,
            reason="Selected counselor has no valid active manager with enabled non-Administrator user",
        )
        decision.update({
            "error": "no_valid_manager",
            "counselor": employee,
            "manager_employee": None,
            "manager_user": None,
        })
        record(
            queue=queue_name,
            stage="COUNSELOR_ASSIGNMENT",
            execution_type="Stage",
            result="FAILED",
            failure_reason=f"Selected counselor {employee} has no valid active manager (reports_to)",
            details=decision,
        )
        meta_debug_log("counselor_assignment_end", lead=lead, employee=None, **context)
        return None

    decision["manager_employee"] = manager_emp
    decision["manager_user"] = manager_user

    # 6. Persist assignment to CRM Lead
    if lead and has_doctype("CRM Lead") and frappe.db.exists("CRM Lead", lead):
        doc = frappe.get_doc("CRM Lead", lead)
        for field in ("assigned_to", "assigned_employee", "counselor", "employee", "assigned_counselor"):
            set_if_has(doc, field, employee)
        if manager_user:
            set_if_has(doc, "assigned_counselor_manager", manager_emp or manager_user)
        doc.save(ignore_permissions=True)

    # 7. Record audit trail
    _assignment_log(lead, employee, queue_name, communication_event, decision)
    _assignment_history(
        lead,
        employee,
        decision.get("strategy") or "round_robin",
        queue_name,
        communication_event,
        decision,
        assignment_type="Automatic Round Robin",
    )

    if queue_doc:
        queue_doc.assigned_employee = employee

    log_info("meta_lead_assigned", lead=lead, employee=employee, department=responsible_department, manager_employee=manager_emp)
    _record_success(queue_name, decision)
    meta_debug_log("counselor_assignment_end", lead=lead, employee=employee, **context)
    return employee


class NotApplicable(RuntimeError):
    """Raised when counselor assignment is not applicable for this department."""
    pass


# ---------------------------------------------------------------------------
# Manager Manual Override
# ---------------------------------------------------------------------------


@frappe.whitelist()
def override_counselor(lead, new_employee, reason=None):
    """
    Manager manual override for counselor assignment.
    Requires System Manager or CRM Manager role.
    """
    _check_override_permission()

    lead = (lead or "").strip()
    new_employee = (new_employee or "").strip()
    reason = (reason or "").strip()

    if not lead or not frappe.db.exists("CRM Lead", lead):
        frappe.throw("CRM Lead not found", frappe.DoesNotExistError)
    if not new_employee or not frappe.db.exists("Employee", new_employee):
        frappe.throw("Employee not found", frappe.DoesNotExistError)

    # Validate employee is active and not Administrator
    emp_data = frappe.db.get_value("Employee", new_employee, ["status", "department", "employee_name", "user_id"], as_dict=True)
    if not emp_data or emp_data.status != "Active":
        frappe.throw(f"Employee {new_employee} is not active", frappe.ValidationError)
    if emp_data.user_id and str(emp_data.user_id).strip().lower() in EXCLUDED_COUNSELOR_USERS:
        frappe.throw(f"Cannot assign system user {emp_data.user_id} as counselor", frappe.ValidationError)

    # Load previous counselor
    prev_employee = frappe.db.get_value("CRM Lead", lead, "assigned_counselor") or \
                    frappe.db.get_value("CRM Lead", lead, "assigned_employee")

    # Update CRM Lead
    crm_doc = frappe.get_doc("CRM Lead", lead)
    for field in ("assigned_employee", "assigned_counselor"):
        set_if_has(crm_doc, field, new_employee)
    if has_field("CRM Lead", "assignment_status"):
        crm_doc.assignment_status = "Assigned"
    crm_doc.save(ignore_permissions=True)

    # Update associated Lead Intake Queue if it exists
    queue_name = frappe.db.get_value("Lead Intake Queue", {"matched_lead": lead}, "name", order_by="creation desc")
    if queue_name:
        frappe.db.set_value("Lead Intake Queue", queue_name, "assigned_employee", new_employee, update_modified=False)

    # Create override history record
    _assignment_history(
        lead,
        new_employee,
        "manual_override",
        queue_name,
        None,
        {"strategy": "manual_override", "selected": new_employee, "previous": prev_employee, "reason": reason},
        assignment_type="Manual Override",
        previous_counselor=prev_employee,
        override_reason=reason,
    )

    frappe.db.commit()
    log_info(
        "counselor_manual_override",
        lead=lead,
        previous_employee=prev_employee,
        new_employee=new_employee,
        override_by=frappe.session.user,
        reason=reason,
    )

    return {
        "ok": True,
        "lead": lead,
        "previous_counselor": prev_employee,
        "new_counselor": new_employee,
        "assignment_type": "Manual Override",
        "override_by": frappe.session.user,
        "reason": reason,
    }


@frappe.whitelist()
def get_eligible_counselors_for_lead(lead):
    """
    Return the list of eligible counselors for a given CRM Lead.
    Used by the manager override modal to populate the counselor dropdown.
    """
    _check_override_permission()

    if not lead or not frappe.db.exists("CRM Lead", lead):
        frappe.throw("CRM Lead not found", frappe.DoesNotExistError)

    queue_name = frappe.db.get_value("Lead Intake Queue", {"matched_lead": lead}, "name", order_by="creation desc")
    queue_doc = frappe.get_doc("Lead Intake Queue", queue_name) if queue_name else None
    responsible_department = get_responsible_department(queue_doc, lead)

    employees = _eligible_employees_for_department(responsible_department)
    result = []
    for emp in employees:
        data = frappe.db.get_value("Employee", emp, ["employee_name", "department", "user_id"], as_dict=True)
        if data:
            result.append({
                "employee": emp,
                "employee_name": data.employee_name,
                "department": data.department,
                "user_id": data.user_id,
            })
    return {"ok": True, "department": responsible_department, "counselors": result}


# ---------------------------------------------------------------------------
# Round-Robin Core
# ---------------------------------------------------------------------------


def _round_robin_assign(department, queue_doc=None):
    """
    Perform an atomic, durable, department-scoped round-robin assignment.
    """
    if not department:
        return None, {
            "strategy": "round_robin",
            "department": None,
            "candidates": [],
            "selected": None,
            "error": "no_department",
        }

    if not has_doctype("Department Round Robin State"):
        return _legacy_assign(queue_doc)

    employees = _eligible_employees_for_department(department)
    if not employees:
        return None, {
            "strategy": "round_robin",
            "department": department,
            "candidates": [],
            "selected": None,
            "error": "no_eligible_counselors",
        }

    state = _get_or_create_state(department)
    employee, new_index = _atomic_advance(state, employees)

    return employee, {
        "strategy": "round_robin",
        "department": department,
        "selected": employee,
        "index": new_index,
        "total_counselors": len(employees),
        "candidates": employees,
    }


def _get_or_create_state(department):
    """Load or create the round-robin state row for a department."""
    row = frappe.db.sql(
        "SELECT name, department, current_index, last_assigned_employee, lock_token, lock_expires_at FROM `tabDepartment Round Robin State` WHERE department = %s LIMIT 1",
        (department,), as_dict=True
    )
    if row:
        return row[0]
    try:
        frappe.db.sql(
            "INSERT INTO `tabDepartment Round Robin State` (name, department, current_index, creation, modified, modified_by, owner, docstatus) VALUES (%s, %s, 0, NOW(), NOW(), %s, %s, 0)",
            (department, department, frappe.session.user or "System", frappe.session.user or "System"),
        )
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
    row = frappe.db.sql(
        "SELECT name, department, current_index, last_assigned_employee, lock_token, lock_expires_at FROM `tabDepartment Round Robin State` WHERE department = %s LIMIT 1",
        (department,), as_dict=True
    )
    return row[0] if row else frappe._dict(name=department, department=department, current_index=0, last_assigned_employee=None, lock_token=None, lock_expires_at=None)


def _atomic_advance(state, employees):
    """Atomically advance the rotation pointer and return the selected employee."""
    n = len(employees)
    max_attempts = 10
    now_dt = now_datetime()
    import datetime as dt
    expires = now_dt + dt.timedelta(seconds=LOCK_TTL_SECONDS)

    for attempt in range(max_attempts):
        token = uuid.uuid4().hex
        rows = frappe.db.sql(
            """
            UPDATE `tabDepartment Round Robin State`
            SET lock_token = %s,
                lock_expires_at = %s,
                modified = %s
            WHERE name = %s
              AND (lock_token IS NULL OR lock_token = '' OR lock_expires_at <= %s)
            """,
            (token, expires, now_dt, state.name, now_dt),
        )
        acquired = frappe.db._cursor.rowcount == 1
        if acquired:
            break
        import time
        time.sleep(0.05 + attempt * 0.05)
    else:
        token = None

    fresh = frappe.db.get_value(
        "Department Round Robin State",
        state.name,
        ["current_index", "last_assigned_employee"],
        as_dict=True,
    ) or {}
    current_index = int(fresh.get("current_index") or 0)

    new_index = current_index % n
    employee = employees[new_index]
    next_index = (new_index + 1) % n

    if token:
        frappe.db.sql(
            """
            UPDATE `tabDepartment Round Robin State`
            SET current_index = %s,
                last_assigned_employee = %s,
                last_assignment_at = %s,
                lock_token = NULL,
                lock_expires_at = NULL,
                modified = %s
            WHERE name = %s AND lock_token = %s
            """,
            (next_index, employee, now_dt, now_dt, state.name, token),
        )
    else:
        frappe.db.set_value(
            "Department Round Robin State",
            state.name,
            {"current_index": next_index, "last_assigned_employee": employee, "last_assignment_at": now_dt},
            update_modified=True,
        )

    frappe.db.commit()
    return employee, new_index


def _eligible_employees_for_department(department, require_manager=True):
    """
    Return a stable ordered list of active Employee names for a given department.

    Strict Invariants:
    1. Employee status == 'Active'
    2. Employee department matches target department (prefix match handles company suffix variants)
    3. Employee has linked user_id
    4. Employee user_id is NOT in EXCLUDED_COUNSELOR_USERS (e.g. Administrator)
    5. Employee name is NOT in EXCLUDED_COUNSELOR_USERS
    6. Linked User exists and User.enabled == 1
    7. User name is NOT in EXCLUDED_COUNSELOR_USERS
    8. Employee has a valid active manager resolved via Employee.reports_to (when require_manager=True)
    """
    if not has_doctype("Employee") or not department:
        return []

    dept_prefix = str(department).split(" - ")[0].strip() if " - " in str(department) else str(department).strip()

    # Look for employees with department exact match OR prefix match
    filters = [
        ["Employee", "status", "=", "Active"],
        ["Employee", "department", "like", f"{dept_prefix}%"],
    ]

    employees = frappe.get_all("Employee", filters=filters, fields=["name", "user_id", "department"], order_by="name asc")

    valid = []
    for emp in employees:
        emp_name = str(emp.name).strip()
        uid = str(emp.user_id or "").strip()

        # Reject empty user_id or excluded users
        if not uid or uid.lower() in [u.lower() for u in EXCLUDED_COUNSELOR_USERS]:
            continue
        if emp_name.lower() in [u.lower() for u in EXCLUDED_COUNSELOR_USERS]:
            continue

        # User must exist and be enabled
        user_data = frappe.db.get_value("User", uid, ["enabled", "name"], as_dict=True)
        if not user_data or not user_data.get("enabled"):
            continue
        if str(user_data.get("name", "")).strip().lower() in [u.lower() for u in EXCLUDED_COUNSELOR_USERS]:
            continue

        # Manager validation: employee must have a valid manager to be eligible for assignment
        if require_manager:
            mgr_emp, mgr_user = _resolve_manager(emp_name)
            if not mgr_emp or not mgr_user:
                continue

        valid.append(emp.name)

    return valid


def _resolve_manager(employee_name):
    """
    Resolve the manager for a given Employee using the canonical ``reports_to``
    field (Link -> Employee).

    Returns (manager_employee_name, manager_user_id) if a valid active manager
    with a non-excluded, enabled User exists. Returns (None, None) if:
    - The employee has no reports_to set
    - reports_to points to an inactive employee
    - The manager's user_id is Administrator or another excluded user
    - The manager's User is disabled
    - Self-reporting cycle (reports_to == employee_name)

    NEVER falls back to "Administrator" as a manager.
    """
    if not employee_name or not has_doctype("Employee"):
        return None, None

    mgr_emp = frappe.db.get_value("Employee", employee_name, "reports_to")
    if not mgr_emp or mgr_emp == employee_name:
        return None, None

    if str(mgr_emp).strip().lower() in [u.lower() for u in EXCLUDED_COUNSELOR_USERS]:
        return None, None

    mgr_data = frappe.db.get_value(
        "Employee", mgr_emp, ["status", "user_id", "employee_name"], as_dict=True
    )
    if not mgr_data or mgr_data.get("status") != "Active":
        return None, None

    mgr_uid = str(mgr_data.get("user_id") or "").strip()
    if not mgr_uid or mgr_uid.lower() in [u.lower() for u in EXCLUDED_COUNSELOR_USERS]:
        return None, None

    mgr_user = frappe.db.get_value("User", mgr_uid, ["enabled", "name"], as_dict=True)
    if not mgr_user or not mgr_user.get("enabled"):
        return None, None
    if str(mgr_user.get("name", "")).strip().lower() in [u.lower() for u in EXCLUDED_COUNSELOR_USERS]:
        return None, None

    return mgr_emp, mgr_uid


# ---------------------------------------------------------------------------
# Legacy / Fallback
# ---------------------------------------------------------------------------


def _legacy_assign(queue_doc=None):
    """Legacy least-workload assignment used as fallback if DocType not migrated."""
    employees = _eligible_employees()
    if not employees:
        return None, {"strategy": "legacy_fallback", "selected": None, "error": "no_employees"}
    employee = _least_workload_employee(employees)
    return employee, {"strategy": "legacy_fallback", "selected": employee}


def _least_workload_employee(employees=None):
    employees = employees or _eligible_employees()
    if not employees:
        return None
    if not has_doctype("Lead Assignment"):
        return employees[0]
    counts = {
        e: frappe.db.count("Lead Assignment", {"assigned_to": e, "status": ["in", ["Pending", "Accepted", "In Progress"]]})
        for e in employees
    }
    return sorted(counts, key=lambda e: (counts[e], e))[0]


def _eligible_employees():
    """Legacy: all active non-Administrator employees."""
    if not has_doctype("Employee"):
        return []
    filters = {"status": "Active"} if has_field("Employee", "status") else {}
    emps = frappe.get_all("Employee", filters=filters, fields=["name", "user_id"], order_by="name asc")
    valid = []
    for e in emps:
        uid = str(e.user_id or "").strip()
        if uid and uid.lower() not in [u.lower() for u in EXCLUDED_COUNSELOR_USERS]:
            valid.append(e.name)
    return valid


# ---------------------------------------------------------------------------
# Audit / Logging
# ---------------------------------------------------------------------------


def _assignment_log(lead, employee, queue_name=None, communication_event=None, decision=None):
    if not employee or not has_doctype("Lead Assignment"):
        return
    if not lead and not queue_name:
        return
    lead_val = lead or f"QUEUE-{queue_name}"
    key = f"assignment:{queue_name}" if queue_name else None
    existing = (
        frappe.db.exists("Lead Assignment", {"meta_intake_key": key})
        if key and has_field("Lead Assignment", "meta_intake_key")
        else None
    )
    if not existing and lead:
        existing = frappe.db.exists(
            "Lead Assignment",
            {"lead": lead, "assigned_to": employee, "status": ["in", ["Pending", "Accepted", "In Progress"]]},
        )
    if existing:
        return
    doc = frappe.new_doc("Lead Assignment")
    doc.lead = lead_val
    doc.assigned_to = employee
    assigned_by = _link_value(doc, "assigned_by")
    if assigned_by:
        doc.assigned_by = assigned_by
    doc.assigned_on = now()
    doc.status = "Pending"
    doc.priority = "Medium"
    set_if_has(doc, "meta_intake_key", key)
    set_if_has(doc, "lead_intake_queue", queue_name)
    set_if_has(doc, "communication_event", communication_event)
    set_if_has(doc, "assignment_decision_json", safe_json_dumps(decision or {}))
    doc.flags.ignore_links = True
    doc.insert(ignore_permissions=True)


def _assignment_history(
    lead,
    employee,
    strategy,
    queue_name=None,
    communication_event=None,
    decision=None,
    assignment_type="Automatic Round Robin",
    previous_counselor=None,
    override_reason=None,
):
    if not lead or not employee or not has_doctype("Counselor Assignment History"):
        return
    key = f"assignment-history:{queue_name}:{assignment_type}" if queue_name else None
    if (
        key
        and has_field("Counselor Assignment History", "meta_intake_key")
        and frappe.db.exists("Counselor Assignment History", {"meta_intake_key": key})
    ):
        return
    doc = frappe.new_doc("Counselor Assignment History")
    for field, value in {
        "lead": lead,
        "assigned_to": employee,
        "assigned_by": _link_value(doc, "assigned_by"),
        "assigned_on": now(),
        "strategy": strategy,
        "meta_intake_key": key,
        "lead_intake_queue": queue_name,
        "communication_event": communication_event,
        "assignment_decision_json": safe_json_dumps(decision or {}),
        "assignment_type": assignment_type,
        "previous_counselor": previous_counselor,
        "override_reason": override_reason,
        "override_by": frappe.session.user if assignment_type == "Manual Override" else None,
    }.items():
        set_if_has(doc, field, value)
    doc.flags.ignore_links = True
    doc.insert(ignore_permissions=True)


def _record_success(queue_name, decision):
    record(
        queue=queue_name,
        stage="COUNSELOR_ASSIGNMENT",
        execution_type="Stage",
        result="SUCCESS",
        details=decision,
    )


def _link_value(doc, fieldname):
    field = doc.meta.get_field(fieldname)
    if not field or field.fieldtype != "Link" or not field.options:
        return frappe.session.user
    if field.options == "User":
        return frappe.session.user if frappe.db.exists("User", frappe.session.user) else None
    if field.options == "Employee":
        employee = _employee_for_user(frappe.session.user)
        return employee if employee and frappe.db.exists("Employee", employee) else None
    return frappe.session.user if frappe.db.exists(field.options, frappe.session.user) else None


def _employee_for_user(user):
    if not user or not has_doctype("Employee"):
        return None
    for field in ("user_id", "company_email", "personal_email"):
        if has_field("Employee", field):
            found = frappe.db.get_value("Employee", {field: user}, "name")
            if found:
                return found
    return None


def _existing_assignment(queue_name):
    if not queue_name or not has_doctype("Lead Assignment") or not has_field("Lead Assignment", "meta_intake_key"):
        return None
    return frappe.db.get_value(
        "Lead Assignment",
        {"meta_intake_key": f"assignment:{queue_name}"},
        "assigned_to",
    )


def _check_override_permission():
    """Verify caller has System Manager or CRM Manager role."""
    roles = set(frappe.get_roles())
    if not ("System Manager" in roles or "CRM Manager" in roles):
        frappe.throw(
            "Only System Manager or CRM Manager can manually override counselor assignment.",
            frappe.PermissionError,
        )
