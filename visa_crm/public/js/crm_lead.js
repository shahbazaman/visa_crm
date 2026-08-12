/**
 * visa_crm/public/js/crm_lead.js
 * ================================
 * V1 CRM Lead customizations:
 *   - "Change Counselor" button for managers (System Manager / CRM Manager)
 *   - Shows assignment_type label (Automatic Round Robin vs Manual Override)
 */

frappe.ui.form.on("CRM Lead", {
    refresh: function (frm) {
        _add_counselor_override_button(frm);
        _show_assignment_type_badge(frm);
    }
});

function _add_counselor_override_button(frm) {
    // Only show to System Manager or CRM Manager
    const allowed_roles = ["System Manager", "CRM Manager"];
    const user_roles = frappe.user_roles || [];
    const can_override = allowed_roles.some(r => user_roles.includes(r));

    if (!can_override) return;

    frm.add_custom_button(__("Change Counselor"), function () {
        _show_counselor_override_dialog(frm);
    }, __("Actions"));
}

function _show_counselor_override_dialog(frm) {
    const lead = frm.doc.name;

    // First fetch eligible counselors for this lead
    frappe.call({
        method: "visa_crm.api.lead_assignment.get_eligible_counselors_for_lead",
        args: { lead: lead },
        callback: function (r) {
            if (!r.message || !r.message.ok) {
                frappe.msgprint(__("Could not fetch eligible counselors. Please try again."));
                return;
            }
            const data = r.message;
            const counselors = data.counselors || [];

            if (counselors.length === 0) {
                frappe.msgprint(__("No eligible counselors found for this lead's department ({0}). Please create employees in the {0} department first.", [data.department || "Unknown"]));
                return;
            }

            const options = counselors.map(c => ({
                value: c.employee,
                label: `${c.employee_name} (${c.department || "Unknown Dept"})`
            }));

            // Show current counselor
            const current_counselor = frm.doc.assigned_counselor || frm.doc.assigned_employee;
            const current_info = current_counselor
                ? __("Current: {0}", [current_counselor])
                : __("No counselor currently assigned");

            const dialog = new frappe.ui.Dialog({
                title: __("Change Counselor"),
                fields: [
                    {
                        label: __("Current Assignment"),
                        fieldtype: "HTML",
                        options: `<div class="alert alert-info" style="margin-bottom: 8px;">
                            ${current_info}
                        </div>`
                    },
                    {
                        label: __("New Counselor"),
                        fieldname: "new_employee",
                        fieldtype: "Select",
                        reqd: 1,
                        options: options.map(o => o.value).join("\n"),
                        description: __("Select from eligible counselors for department: {0}", [data.department || "Unknown"]),
                    },
                    {
                        label: __("Reason"),
                        fieldname: "reason",
                        fieldtype: "Small Text",
                        placeholder: __("e.g. Employee on leave, Special request, Workload balancing"),
                        description: __("Optional: reason for manual override")
                    }
                ],
                primary_action_label: __("Assign Counselor"),
                primary_action: function (values) {
                    if (!values.new_employee) {
                        frappe.msgprint(__("Please select a counselor"));
                        return;
                    }
                    frappe.call({
                        method: "visa_crm.api.lead_assignment.override_counselor",
                        args: {
                            lead: lead,
                            new_employee: values.new_employee,
                            reason: values.reason || "",
                        },
                        callback: function (r) {
                            dialog.hide();
                            if (r.message && r.message.ok) {
                                frappe.show_alert({
                                    message: __("Counselor changed to {0}", [values.new_employee]),
                                    indicator: "green"
                                });
                                frm.reload_doc();
                            } else {
                                frappe.msgprint(__("Failed to change counselor. Please try again."));
                            }
                        }
                    });
                }
            });

            dialog.show();
        }
    });
}

function _show_assignment_type_badge(frm) {
    // Show a small indicator if the lead has assignment_type
    // The assignment type is stored in Counselor Assignment History
    // We show it in the form as a helper
    const counselor = frm.doc.assigned_counselor || frm.doc.assigned_employee;
    if (!counselor) return;

    // Try to fetch the latest assignment history
    frappe.db.get_value("Counselor Assignment History", {
        lead: frm.doc.name,
        assigned_to: counselor,
    }, "assignment_type").then(r => {
        if (r && r.message && r.message.assignment_type) {
            const type = r.message.assignment_type;
            const color = type === "Manual Override" ? "orange" : "green";
            const icon = type === "Manual Override" ? "⚠️" : "🤖";
            const html = `<div style="margin-top: 4px;">
                <span class="indicator ${color}" style="font-size: 12px;">
                    ${icon} ${type}
                </span>
            </div>`;
            // Add after the counselor field label if it exists
            if (frm.fields_dict.assigned_counselor) {
                frm.fields_dict.assigned_counselor.$wrapper
                    .find(".control-value")
                    .append(html);
            }
        }
    }).catch(() => {
        // Silently fail if history not available
    });
}
