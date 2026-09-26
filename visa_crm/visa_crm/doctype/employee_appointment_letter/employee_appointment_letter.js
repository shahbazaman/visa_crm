frappe.ui.form.on('Employee Appointment Letter', {
    refresh: function(frm) {
        if (!frm.is_new()) {
            // Determine default print format based on company/template
            let isHolidays = (frm.doc.company_name_display || '').toLowerCase().includes('holiday') ||
                             (frm.doc.company || '').toLowerCase().includes('holiday');
            let defaultFormat = isHolidays ? 'Employee Holidays Appointment Letter' : 'Employee Travels Appointment Letter';

            // Primary Action: Open the exact pixel-perfect 7-page printview
            frm.add_custom_button(__('Print Exact Appointment Letter'), function() {
                const url = `/printview?doctype=Employee Appointment Letter&name=${encodeURIComponent(frm.doc.name)}&format=${encodeURIComponent(defaultFormat)}&no_letterhead=1`;
                window.open(url, '_blank');
            }).addClass('btn-primary');

            // Secondary option to print either template
            frm.add_custom_button(__('Print Travels Template'), function() {
                const url = `/printview?doctype=Employee Appointment Letter&name=${encodeURIComponent(frm.doc.name)}&format=Middle East Travels Appointment Letter&no_letterhead=1`;
                window.open(url, '_blank');
            }, __('Print Formats'));

            frm.add_custom_button(__('Print Holidays Template'), function() {
                const url = `/printview?doctype=Employee Appointment Letter&name=${encodeURIComponent(frm.doc.name)}&format=Middle East Holidays Appointment Letter&no_letterhead=1`;
                window.open(url, '_blank');
            }, __('Print Formats'));
        }
    },

    employee: function(frm) {
        if (frm.doc.employee) {
            frappe.db.get_doc('Employee', frm.doc.employee).then(emp => {
                frm.set_value('employee_name', emp.employee_name);
                let firstName = emp.first_name || (emp.employee_name ? emp.employee_name.split(' ')[0] : '');
                frm.set_value('first_name', firstName);
                if (emp.salutation) frm.set_value('salutation_title', emp.salutation);
                frm.set_value('salutation', 'Dear ' + (emp.salutation || 'Ms.') + ' ' + firstName + ',');
                if (emp.designation) frm.set_value('designation', emp.designation);
                if (emp.department) frm.set_value('department', emp.department);
                if (emp.date_of_joining) frm.set_value('date_of_joining', emp.date_of_joining);
                if (emp.custom_monthly_salary) {
                    frm.set_value('monthly_salary', emp.custom_monthly_salary);
                    frm.trigger('monthly_salary');
                }
                let addr = emp.current_address || emp.permanent_address || '';
                if (addr) frm.set_value('address', addr);
            });
        }
    },

    monthly_salary: function(frm) {
        if (frm.doc.monthly_salary) {
            let sal = Number(frm.doc.monthly_salary);
            let annual = sal * 12;
            frm.set_value('annual_ctc', annual);

            // Populate Annexure I default values if not manually edited
            let basicM = Math.round(sal * 0.50);
            let daM = Math.round(sal * 0.10);
            let hraM = Math.round(sal * 0.20);
            let otherM = Math.round(sal * 0.20);

            frm.set_value('basic_salary_monthly', basicM);
            frm.set_value('basic_salary_annual', basicM * 12);
            frm.set_value('da_monthly', daM);
            frm.set_value('da_annual', daM * 12);
            frm.set_value('hra_monthly', hraM);
            frm.set_value('hra_annual', hraM * 12);
            frm.set_value('other_allowances_monthly', otherM);
            frm.set_value('other_allowances_annual', otherM * 12);
            frm.set_value('gross_salary_monthly', sal);
            frm.set_value('gross_salary_annual', annual);
            frm.set_value('employer_pf_monthly', 'NA');
            frm.set_value('employer_pf_annual', 'NA');
            frm.set_value('employer_esi_monthly', 'NA');
            frm.set_value('employer_esi_annual', 'NA');
            frm.set_value('ctc_monthly', sal);
            frm.set_value('ctc_annual', annual);
        }
    },

    appointment_letter_template: function(frm) {
        if (frm.doc.appointment_letter_template) {
            frappe.call({
                method: 'frappe.client.get',
                args: {
                    doctype: 'Appointment Letter Template',
                    name: frm.doc.appointment_letter_template
                },
                callback: function(r) {
                    if (r.message) {
                        let tmpl = r.message;
                        let desig = frm.doc.designation || 'Accounts Assistant';
                        let comp = frm.doc.company_name_display || tmpl.company_name_display || 'Middle East Travels & Tourism';
                        let title = frm.doc.salutation_title || 'Ms.';
                        let fname = frm.doc.first_name || (frm.doc.employee_name ? frm.doc.employee_name.split(' ')[0] : 'Candidate');
                        let empName = frm.doc.employee_name || 'Candidate';
                        let sal = frm.doc.monthly_salary ? Number(frm.doc.monthly_salary).toLocaleString('en-IN') : '15,000';
                        let salWords = frm.doc.monthly_salary_in_words || 'Rupees Fifteen Thousand Only';
                        let doj = frm.doc.date_of_joining ? frappe.datetime.str_to_user(frm.doc.date_of_joining) : '17.08.2026';
                        let prob = frm.doc.probation_period || 'three (3) months';
                        let hrs = frm.doc.working_hours || '10:00 AM to 5:30 PM';
                        let days = frm.doc.working_days || 'Monday to Saturday';
                        let lunch = frm.doc.lunch_break || 'forty (40) minute lunch break between 1:00 PM and 2:30 PM';
                        let posting = frm.doc.posting_location || 'Calicut';

                        function sub(txt) {
                            if (!txt) return '';
                            return txt.replace(/{designation}/g, desig)
                                      .replace(/{company}/g, comp)
                                      .replace(/{company_name}/g, comp)
                                      .replace(/{salutation_title}/g, title)
                                      .replace(/{first_name}/g, fname)
                                      .replace(/{employee_name}/g, empName)
                                      .replace(/{monthly_salary}/g, sal)
                                      .replace(/{monthly_salary_in_words}/g, salWords)
                                      .replace(/{date_of_joining}/g, doj)
                                      .replace(/{probation_period}/g, prob)
                                      .replace(/{working_hours}/g, hrs)
                                      .replace(/{working_days}/g, days)
                                      .replace(/{lunch_break}/g, lunch)
                                      .replace(/{posting_location}/g, posting);
                        }

                        frm.set_value('salutation', 'Dear ' + title + ' ' + fname + ',');
                        frm.set_value('introduction', sub(tmpl.introduction));
                        frm.set_value('clause_1_appointment_scope', sub(tmpl.clause_1_appointment_scope));
                        frm.set_value('clause_2_classification', sub(tmpl.clause_2_classification));
                        frm.set_value('clause_3_probation', sub(tmpl.clause_3_probation));
                        frm.set_value('clause_4_working_hours', sub(tmpl.clause_4_working_hours));
                        frm.set_value('clause_5_leave_policy', sub(tmpl.clause_5_leave_policy));
                        frm.set_value('clause_6_compensation', sub(tmpl.clause_6_compensation));
                        frm.set_value('clause_7_duties_conduct', sub(tmpl.clause_7_duties_conduct));
                        frm.set_value('clause_8_dress_code', sub(tmpl.clause_8_dress_code));
                        frm.set_value('clause_9_confidentiality', sub(tmpl.clause_9_confidentiality));
                        frm.set_value('clause_10_transfer', sub(tmpl.clause_10_transfer));
                        frm.set_value('clause_11_resignation_termination', sub(tmpl.clause_11_resignation_termination));
                        frm.set_value('clause_12_general_terms', sub(tmpl.clause_12_general_terms));
                        frm.set_value('clause_13_policy_compliance', sub(tmpl.clause_13_policy_compliance));
                        frm.set_value('clause_14_acceptance', sub(tmpl.clause_14_acceptance));
                        frm.set_value('acceptance_statement', sub(tmpl.acceptance_statement));

                        if (tmpl.default_hr_signatory_name) frm.set_value('hr_signatory_name', tmpl.default_hr_signatory_name);
                        if (tmpl.default_hr_signatory_designation) frm.set_value('hr_signatory_designation', tmpl.default_hr_signatory_designation);
                        if (tmpl.default_hr_signatory_title) frm.set_value('hr_signatory_title', tmpl.default_hr_signatory_title);
                        if (tmpl.signatory_company_label) frm.set_value('signatory_company_label', tmpl.signatory_company_label);
                        if (tmpl.company_logo && !frm.doc.company_logo) frm.set_value('company_logo', tmpl.company_logo);
                        if (tmpl.iata_logo && !frm.doc.iata_logo) frm.set_value('iata_logo', tmpl.iata_logo);
                        if (tmpl.signature_image && !frm.doc.signature_image) frm.set_value('signature_image', tmpl.signature_image);
                    }
                }
            });
        }
    }
});
