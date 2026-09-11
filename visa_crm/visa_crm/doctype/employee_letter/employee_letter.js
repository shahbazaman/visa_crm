frappe.ui.form.on('Employee Letter', {
    refresh: function(frm) {
        if (!frm.is_new() && frm.doc.status === 'Issued') {
            frm.add_custom_button(__('Download PDF'), function() {
                const url = `/api/method/frappe.utils.print_format.download_pdf?doctype=Employee Letter&name=${encodeURIComponent(frm.doc.name)}&format=Standard`;
                window.open(url);
            }, __('Actions'));
        }
    },
    letter_type: function(frm) {
        if (frm.doc.letter_type === 'Offer Letter') {
            frm.set_value('naming_series', 'OFFER-.YYYY.-.#####');
        } else if (frm.doc.letter_type === 'Appointment Letter') {
            frm.set_value('naming_series', 'APPT-.YYYY.-.#####');
        } else if (frm.doc.letter_type === 'Increment Letter') {
            frm.set_value('naming_series', 'INCR-.YYYY.-.#####');
        }
    },
    employee: function(frm) {
        if (frm.doc.employee) {
            frappe.db.get_doc('Employee', frm.doc.employee).then(emp => {
                frm.set_value('applicant_name', emp.employee_name);
                frm.set_value('designation', emp.designation);
                frm.set_value('department', emp.department);
                frm.set_value('date_of_joining', emp.date_of_joining);
                frm.set_value('work_location', emp.branch || 'Main Office');
                frm.set_value('reporting_manager', emp.reports_to);
                frm.set_value('previous_salary', emp.custom_monthly_salary || 0);
            });
        }
    },
    new_salary: function(frm) {
        if (frm.doc.previous_salary && frm.doc.new_salary) {
            let prev = parseFloat(frm.doc.previous_salary);
            let next = parseFloat(frm.doc.new_salary);
            let diff = next - prev;
            frm.set_value('increment_amount', diff);
            if (prev > 0) {
                frm.set_value('increment_percentage', parseFloat(((diff / prev) * 100).toFixed(2)));
            }
        }
    }
});
