frappe.ui.form.on('Employee Offer Letter', {
    refresh: function(frm) {
        if (!frm.is_new() && frm.doc.status === 'Issued') {
            frm.add_custom_button(__('Download PDF'), function() {
                const url = `/api/method/frappe.utils.print_format.download_pdf?doctype=Employee Offer Letter&name=${encodeURIComponent(frm.doc.name)}&format=Middle East Travels Offer Letter`;
                window.open(url);
            }, __('Actions'));
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
                        let fname = frm.doc.first_name || 'Candidate';
                        let sal = frm.doc.monthly_salary ? frm.doc.monthly_salary.toLocaleString('en-IN') : '18,000';
                        let salWords = frm.doc.monthly_salary_in_words || 'Rupees Eighteen Thousand Only';
                        let doj = frm.doc.date_of_joining || '11.09.2026';

                        function sub(txt) {
                            if (!txt) return '';
                            return txt.replace(/{designation}/g, desig)
                                      .replace(/{company}/g, comp)
                                      .replace(/{first_name}/g, fname)
                                      .replace(/{monthly_salary}/g, sal)
                                      .replace(/{monthly_salary_in_words}/g, salWords)
                                      .replace(/{date_of_joining}/g, doj);
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
                    }
                }
            });
        }
    }
});
