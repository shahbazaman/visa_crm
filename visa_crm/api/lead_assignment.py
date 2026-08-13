"""
visa_crm/api/lead_assignment.py
================================
V1 Department-Aware Round-Robin Counselor Assignment + Manager Manual Override.

Architecture:
- Supported departments (Holidays, Global Visa): use persistent per-department
  round-robin stored in ``Department Round Robin State`` DocType.
- Unsupported departments (Reservation, Digital Marketer, Social Media, etc.):
  return NOT_APPLICABLE — pipeline stage finishes cleanly without a counselor.
- Manager override: whitelisted API with CRM Manager / System Manager permission.
- Concurrency: uses optimistic DB-level lock token on Department Round Robin State.
- Idempotent: existing assignment (via Lead Assignment meta_intake_key) is reused.
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
# Public constants
# ---------------------------------------------------------------------------

#: Department name prefixes that receive automatic round-robin assignment in V1.
#: Any Frappe department whose name starts with one of these prefixes is eligible.
#: This handles company-suffix variants like "Holidays - HNC" or "Global Visa - Client".
SUPPORTED_DEPARTMENT_PREFIXES = {"Holidays", "Global Visa"}
SUPPORTED_DEPARTMENTS = SUPPORTED_DEPARTMENT_PREFIXES


def is_supported_department(department):
    """Return True if department is supported for automatic round-robin assignment."""
    if not department:
        return False
    dept_lower = department.strip().lower()
    return any(dept_lower == p.lower() or dept_lower.startswith(p.lower() + " ")
               for p in SUPPORTED_DEPARTMENT_PREFIXES)

#: How long (seconds) to hold the round-robin lock before expiry.
LOCK_TTL_SECONDS = 30

#: How old (minutes) the eligible counselor cache may be before it's refreshed.
CACHE_TTL_MINUTES = 60


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------


def assign_lead(lead, queue_doc=None, strategy=None, context=None, communication_event=None):
    """
    Primary entry point called by the pipeline COUNSELOR_ASSIGNMENT stage.

    Returns the assigned Employee name, or ``None`` if no counselor is available.
    Raises ``NotApplicable`` if the department is not supported in V1 (caller
    should mark the stage as NOT_APPLICABLE rather than FAILED).
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

    # 2. Determine department
    responsible_department = _get_responsible_department(queue_doc, lead)

    # 3. Route by department support
    if responsible_department and not is_supported_department(responsible_department):
        # Unsupported department — raise sentinel so caller marks NOT_APPLICABLE
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
            failure_reason="No eligible counselor found for department",
            details=decision,
        )
        meta_debug_log("counselor_assignment_end", lead=lead, employee=None, **context)
        return None

    # 5. Persist assignment to CRM Lead
    if lead and has_doctype("CRM Lead"):
        doc = frappe.get_doc("CRM Lead", lead)
        for field in ("assigned_to", "assigned_employee", "counselor", "employee", "assigned_counselor"):
            set_if_has(doc, field, employee)
        doc.save(ignore_permissions=True)

    # 6. Record audit trail
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

    log_info("meta_lead_assigned", lead=lead, employee=employee, department=responsible_department)
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

    Does NOT advance the automatic round-robin rotation — the round-robin
    continues independently from its current position.

    Returns a dict with the override result.
    """
    _check_override_permission()

    lead = (lead or "").strip()
    new_employee = (new_employee or "").strip()
    reason = (reason or "").strip()

    if not lead or not frappe.db.exists("CRM Lead", lead):
        frappe.throw("CRM Lead not found", frappe.DoesNotExistError)
    if not new_employee or not frappe.db.exists("Employee", new_employee):
        frappe.throw("Employee not found", frappe.DoesNotExistError)

    # Validate employee is active
    emp_data = frappe.db.get_value("Employee", new_employee, ["status", "department", "employee_name"], as_dict=True)
    if not emp_data or emp_data.status != "Active":
        frappe.throw(f"Employee {new_employee} is not active", frappe.ValidationError)

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

    # Update associated Lead Assignment if it exists
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

    # Get department from CRM Lead's queue
    queue_name = frappe.db.get_value("Lead Intake Queue", {"matched_lead": lead}, "name", order_by="creation desc")
    responsible_department = None
    if queue_name:
        responsible_department = frappe.db.get_value("Lead Intake Queue", queue_name, "responsible_department")
    if not responsible_department:
        responsible_department = frappe.db.get_value("CRM Lead", lead, "responsible_department")

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

    Uses a lock token on ``Department Round Robin State`` to prevent two
    concurrent workers from receiving the same rotation slot.

    Returns (employee_name, decision_dict).
    """
    if not has_doctype("Department Round Robin State"):
        # Fallback to legacy least_workload if DocType not yet migrated
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
    """Load or create the round-robin state row for a department. Returns a frappe._dict."""
    row = frappe.db.sql(
        "SELECT name, department, current_index, last_assigned_employee, lock_token, lock_expires_at FROM `tabDepartment Round Robin State` WHERE department = %s LIMIT 1",
        (department,), as_dict=True
    )
    if row:
        return row[0]
    # Create new row via SQL to avoid module import issues
    try:
        frappe.db.sql(
            "INSERT INTO `tabDepartment Round Robin State` (name, department, current_index, creation, modified, modified_by, owner, docstatus) VALUES (%s, %s, 0, NOW(), NOW(), 'Administrator', 'Administrator', 0)",
            (department, department),
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
    """
    Atomically advance the rotation pointer and return the selected employee.

    Uses an UPDATE WHERE lock_token IS NULL (or expired) pattern to prevent
    concurrent workers from taking the same slot.

    Returns (employee_name, new_index).
    """
    n = len(employees)
    max_attempts = 10
    now_dt = now_datetime()
    expires = now_dt.replace(microsecond=0)
    import datetime as dt
    expires = now_dt + dt.timedelta(seconds=LOCK_TTL_SECONDS)

    for attempt in range(max_attempts):
        # Try to acquire lock
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
        # Brief back-off before retry
        import time
        time.sleep(0.05 + attempt * 0.05)
    else:
        # Could not acquire lock — fall back to reading current state without lock
        frappe.logger("visa_crm.assignment").warning(
            f"Could not acquire round-robin lock for {state.name} after {max_attempts} attempts"
        )
        token = None

    # Reload state to get latest index
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

    # Update state
    update_values = {
        "current_index": next_index,
        "last_assigned_employee": employee,
        "last_assignment_at": now_dt,
        "lock_token": None,
        "lock_expires_at": None,
    }
    if token:
        # Release our lock and update index atomically
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


def _eligible_employees_for_department(department):
    """
    Return a stable ordered list of active Employee names for a given department.

    Employees must be:
    - Status = Active
    - Assigned to the department (prefix matching handles company suffixes like 'Holidays - HNC')
    - Have a valid user_id (required for CRM access)

    Returns list sorted by ``name`` asc for determinism.
    """
    if not has_doctype("Employee"):
        return []

    filters = [["Employee", "status", "=", "Active"]]
    if department:
        filters.append(["Employee", "department", "like", f"{department}%"])

    employees = frappe.get_all("Employee", filters=filters, fields=["name", "user_id"], order_by="name asc")

    valid = []
    for emp in employees:
        if emp.user_id and frappe.db.exists("User", emp.user_id):
            valid.append(emp.name)



    return valid


def _get_responsible_department(queue_doc, lead=None):
    """
    Extract responsible_department from queue_doc, or fall back to CRM Lead.
    """
    if queue_doc:
        dept = getattr(queue_doc, "responsible_department", None)
        if dept:
            return dept
    if lead and has_doctype("CRM Lead") and has_field("CRM Lead", "responsible_department"):
        return frappe.db.get_value("CRM Lead", lead, "responsible_department")
    return None


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
    """Legacy: all active employees (used as fallback)."""
    if not has_doctype("Employee"):
        return []
    configured = frappe.conf.get("visa_crm_sales_employees")
    if configured:
        return [e for e in configured if frappe.db.exists("Employee", e)]
    filters = {"status": "Active"} if has_field("Employee", "status") else {}
    return frappe.get_all("Employee", filters=filters, pluck="name", order_by="name asc")


# ---------------------------------------------------------------------------
# Audit / Logging
# ---------------------------------------------------------------------------


def _assignment_log(lead, employee, queue_name=None, communication_event=None, decision=None):
    if not lead or not employee or not has_doctype("Lead Assignment"):
        return
    key = f"assignment:{queue_name}" if queue_name else None
    existing = (
        frappe.db.exists("Lead Assignment", {"meta_intake_key": key})
        if key and has_field("Lead Assignment", "meta_intake_key")
        else None
    )
    existing = existing or frappe.db.exists(
        "Lead Assignment",
        {"lead": lead, "assigned_to": employee, "status": ["in", ["Pending", "Accepted", "In Progress"]]},
    )
    if existing:
        return
    doc = frappe.new_doc("Lead Assignment")
    doc.lead = lead
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
