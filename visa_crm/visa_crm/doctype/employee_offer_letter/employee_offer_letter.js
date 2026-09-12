frappe.ui.form.on('Employee Offer Letter', {
    refresh: function(frm) {
        if (!frm.is_new()) {
            // Primary Action: Opens the exact perfect format print preview (where user can print or save as PDF with 100% fidelity)
            frm.add_custom_button(__('Print Exact Offer Letter'), function() {
                const url = `/printview?doctype=Employee Offer Letter&name=${encodeURIComponent(frm.doc.name)}&format=Middle East Travels Offer Letter&no_letterhead=1`;
                window.open(url, '_blank');
            }).addClass('btn-primary');
        }
    },
    employee: function(frm) {
        if (frm.doc.employee) {
            frappe.db.get_doc('Employee', frm.doc.employee).then(emp => {
                frm.set_value('employee_name', emp.employee_name);
                let firstName = emp.first_name || (emp.employee_name ? emp.employee_name.split(' ')[0] : '');
                frm.set_value('first_name', firstName);
                frm.set_value('salutation', 'Dear Mr./Ms. ' + firstName + ',');
                if (emp.designation) frm.set_value('designation', emp.designation);
                if (emp.department) frm.set_value('department', emp.department);
                if (emp.date_of_joining) frm.set_value('date_of_joining', emp.date_of_joining);
                if (emp.custom_monthly_salary) frm.set_value('monthly_salary', emp.custom_monthly_salary);
                if (emp.custom_is_on_probation !== undefined) frm.set_value('probation', emp.custom_is_on_probation);
                let addr = emp.current_address || emp.permanent_address || '';
                if (addr) frm.set_value('address', addr);
            });
        }
    },
    offer_letter_template: function(frm) {
        if (frm.doc.offer_letter_template) {
            frappe.call({
                method: 'frappe.client.get',
                args: {
                    doctype: 'Offer Letter Template',
                    name: frm.doc.offer_letter_template
                },
                callback: function(r) {
                    if (r.message) {
                        let tmpl = r.message;
                        let desig = frm.doc.designation || 'Sales & Marketing Executive';
                        let comp = frm.doc.company_name_display || tmpl.company_name_display || 'Middle East Travels & Tourism';
                        let fname = frm.doc.first_name || (frm.doc.employee_name ? frm.doc.employee_name.split(' ')[0] : 'Candidate');
                        let empName = frm.doc.employee_name || 'Candidate';
                        let sal = frm.doc.monthly_salary ? Number(frm.doc.monthly_salary).toLocaleString('en-IN') : '18,000';
                        let salWords = frm.doc.monthly_salary_in_words || 'Rupees Eighteen Thousand Only';
                        let doj = frm.doc.date_of_joining ? frappe.datetime.str_to_user(frm.doc.date_of_joining) : '11.09.2026';
                        let prob = frm.doc.probation_period || 'three (3) months';
                        let hrs = frm.doc.working_hours || 'Monday to Saturday, 10:00 AM to 5:30 PM';
                        let time = frm.doc.joining_time || '10:30 AM';
                        let notice = frm.doc.notice_period || 'One (1) month’s written notice or salary in lieu thereof';
                        let leave = frm.doc.leave_entitlement || 'Two (2) paid leaves per month (1 paid leave during probation)';

                        function sub(txt) {
                            if (!txt) return '';
                            return txt.replace(/{designation}/g, desig)
                                      .replace(/{company}/g, comp)
                                      .replace(/{first_name}/g, fname)
                                      .replace(/{employee_name}/g, empName)
                                      .replace(/{monthly_salary}/g, sal)
                                      .replace(/{monthly_salary_in_words}/g, salWords)
                                      .replace(/{date_of_joining}/g, doj)
                                      .replace(/{joining_date_formatted}/g, doj)
                                      .replace(/{probation_period}/g, prob)
                                      .replace(/{working_hours}/g, hrs)
                                      .replace(/{joining_time}/g, time)
                                      .replace(/{notice_period}/g, notice)
                                      .replace(/{leave_entitlement}/g, leave);
                        }

                        frm.set_value('introduction', sub(tmpl.introduction));
                        frm.set_value('compensation_details', sub(tmpl.compensation_text));
                        frm.set_value('probation_details', sub(tmpl.probation_text));
                        frm.set_value('performance_reviews', sub(tmpl.performance_review_text));
                        frm.set_value('working_hours_details', sub(tmpl.working_hours_text));
                        frm.set_value('leave_details', sub(tmpl.leave_text));
                        frm.set_value('notice_period_details', sub(tmpl.notice_period_text));
                        frm.set_value('joining_details', sub(tmpl.joining_details_text));
                        frm.set_value('required_documents', sub(tmpl.required_documents_text));
                        frm.set_value('acceptance_terms', sub(tmpl.acceptance_text));

                        if (tmpl.default_hr_signatory_name) frm.set_value('hr_signatory_name', tmpl.default_hr_signatory_name);
                        if (tmpl.default_hr_signatory_designation) frm.set_value('hr_signatory_designation', tmpl.default_hr_signatory_designation);
                        if (tmpl.company_logo && !frm.doc.company_logo) frm.set_value('company_logo', tmpl.company_logo);
                        if (tmpl.iata_logo && !frm.doc.iata_logo) frm.set_value('iata_logo', tmpl.iata_logo);
                        if (tmpl.signature_image && !frm.doc.signature_image) frm.set_value('signature_image', tmpl.signature_image);
                    }
                }
            });
        }
    }
});
