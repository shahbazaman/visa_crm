// -*- coding: utf-8 -*-
frappe.ui.form.on('Appointment Letter', {
    onload: function(frm) {
        if (!frm.doc.custom_posting_location) {
            frm.set_value('custom_posting_location', 'Calicut');
        }
        if (!frm.doc.custom_salutation_title) {
            frm.set_value('custom_salutation_title', 'Ms.');
        }
        if (!frm.doc.custom_monthly_salary) {
            frm.set_value('custom_monthly_salary', 15000);
        }
    },

    refresh: function(frm) {
        let isHolidays = (frm.doc.company || '').toLowerCase().includes('holiday') ||
                         (frm.doc.appointment_letter_template || '').toLowerCase().includes('holiday');
        let defaultFormat = isHolidays ? 'Middle East Holidays Appointment Letter' : 'Middle East Travels Appointment Letter';

        if (!frm.is_new()) {
            // Primary Action: Open the exact pixel-perfect 7-page printview
            frm.add_custom_button(__('Print Exact Appointment Letter'), function() {
                const url = `/printview?doctype=Appointment Letter&name=${encodeURIComponent(frm.doc.name)}&format=${encodeURIComponent(defaultFormat)}&no_letterhead=1`;
                window.open(url, '_blank');
            }).addClass('btn-primary');

            frm.add_custom_button(__('Print Travels Template'), function() {
                const url = `/printview?doctype=Appointment Letter&name=${encodeURIComponent(frm.doc.name)}&format=Middle East Travels Appointment Letter&no_letterhead=1`;
                window.open(url, '_blank');
            }, __('Print Formats'));

            frm.add_custom_button(__('Print Holidays Template'), function() {
                const url = `/printview?doctype=Appointment Letter&name=${encodeURIComponent(frm.doc.name)}&format=Middle East Holidays Appointment Letter&no_letterhead=1`;
                window.open(url, '_blank');
            }, __('Print Formats'));
        }

        // Action to re-calculate Annexure I Salary Breakdown
        frm.add_custom_button(__('Recalculate Salary Breakdown'), function() {
            calculate_salary_breakdown(frm);
            frappe.show_alert({ message: __('Annexure I Salary Breakdown recalculation completed'), indicator: 'green' });
        }, __('Actions'));

        // Action to load or reload official 14 clauses for editing
        frm.add_custom_button(__('Load / Reset Official Clauses'), function() {
            frappe.confirm(__('This will populate all 14 editable clauses from the official template into the form text fields so you can edit any section. Proceed?'), function() {
                populate_template_defaults(frm, true);
                frappe.show_alert({ message: __('Template clauses loaded into text fields for editing'), indicator: 'green' });
            });
        }, __('Actions'));
    },

    appointment_letter_template: function(frm) {
        populate_template_defaults(frm, false);
    },

    company: function(frm) {
        populate_template_defaults(frm, false);
    },

    custom_monthly_salary: function(frm) {
        calculate_salary_breakdown(frm);
    },

    job_applicant: function(frm) {
        if (frm.doc.job_applicant) {
            frappe.db.get_doc('Job Applicant', frm.doc.job_applicant).then(app => {
                if (app) {
                    if (app.applicant_name && !frm.doc.applicant_name) {
                        frm.set_value('applicant_name', app.applicant_name);
                    }
                    if (app.designation && !frm.doc.custom_designation) {
                        frm.set_value('custom_designation', app.designation);
                    }
                    let addr = app.address || app.location || '';
                    if (addr && !frm.doc.custom_address) {
                        frm.set_value('custom_address', addr);
                    }
                }
            });
        }
    }
});

function calculate_salary_breakdown(frm) {
    let monthly = flt(frm.doc.custom_monthly_salary) || 15000;
    let annual = monthly * 12;

    frm.set_value('custom_annual_ctc', annual);
    frm.set_value('custom_monthly_salary_in_words', get_salary_in_words(monthly));

    let basic_m = Math.round(monthly * 0.5);
    let basic_a = basic_m * 12;
    let da_m = Math.round(monthly * 0.1);
    let da_a = da_m * 12;
    let hra_m = Math.round(monthly * 0.2);
    let hra_a = hra_m * 12;
    let other_m = Math.round(monthly * 0.2);
    let other_a = other_m * 12;

    frm.set_value('custom_basic_salary_monthly', basic_m);
    frm.set_value('custom_basic_salary_annual', basic_a);
    frm.set_value('custom_da_monthly', da_m);
    frm.set_value('custom_da_annual', da_a);
    frm.set_value('custom_hra_monthly', hra_m);
    frm.set_value('custom_hra_annual', hra_a);
    frm.set_value('custom_other_allowances_monthly', other_m);
    frm.set_value('custom_other_allowances_annual', other_a);

    frm.set_value('custom_gross_salary_monthly', monthly);
    frm.set_value('custom_gross_salary_annual', annual);

    if (!frm.doc.custom_employer_pf_monthly) frm.set_value('custom_employer_pf_monthly', 'NA');
    if (!frm.doc.custom_employer_pf_annual) frm.set_value('custom_employer_pf_annual', 'NA');
    if (!frm.doc.custom_employer_esi_monthly) frm.set_value('custom_employer_esi_monthly', 'NA');
    if (!frm.doc.custom_employer_esi_annual) frm.set_value('custom_employer_esi_annual', 'NA');

    frm.set_value('custom_ctc_monthly', monthly);
    frm.set_value('custom_ctc_annual', annual);
}

function get_salary_in_words(num) {
    if (!num || isNaN(num)) return 'Rupees Zero Only';
    num = Math.floor(Number(num));
    const a = ['', 'One ', 'Two ', 'Three ', 'Four ', 'Five ', 'Six ', 'Seven ', 'Eight ', 'Nine ', 'Ten ', 'Eleven ', 'Twelve ', 'Thirteen ', 'Fourteen ', 'Fifteen ', 'Sixteen ', 'Seventeen ', 'Eighteen ', 'Nineteen '];
    const b = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety'];
    function numToWords(n) {
        if (n === 0) return '';
        if (n < 20) return a[n];
        if (n < 100) return b[Math.floor(n / 10)] + ((n % 10 !== 0) ? ' ' + a[n % 10] : ' ');
        if (n < 1000) return a[Math.floor(n / 100)] + 'Hundred ' + ((n % 100 !== 0) ? 'and ' + numToWords(n % 100) : '');
        return '';
    }
    let crore = Math.floor(num / 10000000);
    num %= 10000000;
    let lakh = Math.floor(num / 100000);
    num %= 100000;
    let thousand = Math.floor(num / 1000);
    num %= 1000;
    let hundred = num;
    let str = 'Rupees ';
    if (crore > 0) str += numToWords(crore) + 'Crore ';
    if (lakh > 0) str += numToWords(lakh) + 'Lakh ';
    if (thousand > 0) str += numToWords(thousand) + 'Thousand ';
    if (hundred > 0) str += numToWords(hundred);
    str = str.trim() + ' Only';
    return str;
}

function populate_template_defaults(frm, force) {
    let isHolidays = (frm.doc.company || '').toLowerCase().includes('holiday') ||
                     (frm.doc.appointment_letter_template || '').toLowerCase().includes('holiday');

    let compName = isHolidays ? 'Middle East Holidays' : 'Middle East Travels & Tourism';
    let sigLabel = isHolidays ? 'For Middle East Holidays' : 'For Middle East Travels & Tourism';
    let prefix = isHolidays ? 'MEH/HR/AL' : 'METT/HR/AL';
    let emailWeb = isHolidays ? 'info@middleeastholidays.in | www.middleeastholidays.in' : 'info@middleeasttravels.in | www.middleeasttravels.in';

    let year = frm.doc.appointment_date ? frm.doc.appointment_date.split('-')[0] : '2026';
    let refNo = `${prefix}/02/${year}`;

    if (force || !frm.doc.custom_reference_number) {
        frm.set_value('custom_reference_number', refNo);
    }
    if (force || !frm.doc.custom_signatory_company_label) {
        frm.set_value('custom_signatory_company_label', sigLabel);
    }
    if (force || !frm.doc.custom_hr_signatory_name) {
        frm.set_value('custom_hr_signatory_name', 'Gopika');
    }
    if (force || !frm.doc.custom_hr_signatory_designation) {
        frm.set_value('custom_hr_signatory_designation', 'HR Consultant');
    }
    if (force || !frm.doc.custom_hr_signatory_title) {
        frm.set_value('custom_hr_signatory_title', 'Authorized Signatory');
    }
    if (force || !frm.doc.custom_posting_location) {
        frm.set_value('custom_posting_location', 'Calicut');
    }
    if (force || !frm.doc.custom_footer_address) {
        frm.set_value('custom_footer_address', 'Shobha Tower, 5/3412L, Mavoor Rd, near Emerald Mall, Arayidathupalam, Kozhikode, Kerala 673004');
    }
    if (force || !frm.doc.custom_footer_contact) {
        frm.set_value('custom_footer_contact', 'Tel: 91 8593944666, 91 7025144666');
    }
    if (force || !frm.doc.custom_footer_email_web) {
        frm.set_value('custom_footer_email_web', emailWeb);
    }
    if (force || !frm.doc.custom_probation_period) {
        frm.set_value('custom_probation_period', 'three (3) months');
    }
    if (force || !frm.doc.custom_working_hours) {
        frm.set_value('custom_working_hours', '10:00 AM to 5:30 PM');
    }
    if (force || !frm.doc.custom_working_days) {
        frm.set_value('custom_working_days', 'Monday to Saturday');
    }
    if (force || !frm.doc.custom_lunch_break) {
        frm.set_value('custom_lunch_break', 'forty (40) minute lunch break between 1:00 PM and 2:30 PM');
    }

    if (!frm.doc.custom_annual_ctc || force) {
        calculate_salary_breakdown(frm);
    }

    // Populate clauses with company name
    let desig = frm.doc.custom_designation || 'Accounts Assistant';
    let doj = frm.doc.custom_date_of_joining ? frappe.datetime.str_to_user(frm.doc.custom_date_of_joining) : (frm.doc.appointment_date ? frappe.datetime.str_to_user(frm.doc.appointment_date) : '17.08.2026');
    let loc = frm.doc.custom_posting_location || 'Calicut';

    let default_intro = `We are pleased to appoint you at ${compName}, as ${desig} effective from ${doj}. Your employment shall be governed by the terms and conditions set forth in this Appointment Letter and the Company’s policies, as amended from time to time, and you shall be bound by all such rules, regulations, and procedures as may be prescribed by the Management.`;

    let c1 = `1.1 You are appointed as ${desig} w.e.f. ${doj}, and shall report to your Reporting Manager.
1.2 Your employment shall be governed by the provisions of this Appointment Letter, the Company's HR Policies, Code of Conduct, service rules, administrative instructions, and all applicable laws and statutory regulations, as amended from time to time. You are required to comply with all such policies, rules, and procedures throughout your employment.
1.3 Your initial place of posting shall be the Company's office at ${loc}. However, depending on business requirements, the Company reserves the right to transfer or assign you to any of its offices, branches, or any other place of business.
1.4 You shall diligently perform the duties and responsibilities assigned to you and faithfully discharge all functions relating to your position. The Company reserves the right to modify, expand, or reassign your duties, responsibilities, designation, or reporting structure from time to time based on operational, organizational, or business requirements.`;

    let c2 = `As per Company policy, you shall initially be classified as a Probationary Employee. Upon confirmation, your status shall be converted to Permanent Employee, subject to meeting performance and conduct standards.`;

    let c3 = `3.1 You will be on probation for three (3) months, effective from your date of joining.
3.2 During the probation period, your performance, attendance, punctuality, discipline, conduct, and overall suitability for the role will be continuously monitored and evaluated. Periodic performance reviews may be conducted by your Reporting Manager in coordination with the Human Resources Department.
3.3 Based on your overall performance and the Company's assessment, the Company reserves the right to extend your probation period by up to one (1) to three (3) months, or reduce/waive the remaining probation period.
3.4 In case of performance gaps, a Performance Improvement Plan (PIP) may be issued.
3.5 Confirmation of your employment shall be deemed confirmed only upon issuance of a written Confirmation Letter.
3.6 The Company reserves the right to terminate employment during probation if performance or conduct is unsatisfactory.`;

    let c4 = `4.1 ${compName} follows a six-day work week (Monday to Saturday).
4.2 Standard working hours shall be 10:00 AM to 5:30 PM.
4.3 You shall be entitled to a forty (40) minute lunch break between 1:00 PM and 2:30 PM.`;

    let c5 = `5.1 The Company's leave cycle shall be from 1st January to 31st December of each calendar year.
5.2 Employees under probation shall be entitled to one (1) day of paid leave per month.
5.3 Upon confirmation: Casual Leave (CL) 12 days/year (1/month), Sick Leave (SL) 12 days/year (1/month).
5.4 Other Leave Entitlements as per HR Policy.`;

    let sal_f = Number(frm.doc.custom_monthly_salary || 15000).toLocaleString('en-IN');
    let sal_w = frm.doc.custom_monthly_salary_in_words || 'Rupees Fifteen Thousand Only';
    let c6 = `6.1 You shall be paid a monthly gross salary of ₹${sal_f}/- (${sal_w}), the detailed structure of which is in Annexure I.
6.2 Salary shall be subject to applicable statutory deductions and Company policies.`;

    let c7 = `7.1 Faithfully, honestly, and diligently perform assigned duties and devote full working time to the Company.
7.2 Carry out all lawful instructions issued by the Management and Reporting Manager.
7.3 Comply with Company policies, rules, and statutory regulations.
7.4 Maintain highest standards of integrity, punctuality, confidentiality, and professional conduct.
7.5 Achieve performance standards, KRAs, and KPIs.
7.6 Protect all Company assets, property, records, and systems.
7.7 Do not disclose confidential or proprietary information.
7.8 Do not engage in any other employment or business without prior written approval.
7.9 Maintain respectful relations with colleagues and clients.
7.10 Promptly report misconduct, fraud, or safety hazards.
7.11 Cooperate with modifications in duties or place of work.
7.12 Disciplinary action for policy breach up to termination.`;

    let c8 = `You are required to adhere to professional dress code standards at all times.`;
    let c9 = `You shall maintain strict confidentiality of all Company data, documents, and information at all times, and shall safeguard Company property; promptly return all Company property upon cessation of employment.`;
    let c10 = `The Company reserves the right to transfer or assign you to any department, role, or location based on business needs.`;

    let c11 = `11.1 Either party may terminate employment by giving thirty (30) days' prior written notice or salary in lieu thereof.
11.2 Resignation must be in writing and becomes effective upon written acceptance by Management.
11.3 Diligently perform duties during notice period.
11.4 Complete satisfactory handover of all duties, records, passwords, and assignments.
11.5 Return all Company property before last working day.
11.6 Leave during notice period treated as LOP unless approved under exceptional circumstances.
11.7 Full & Final settlement processed after completion of exit formalities.
11.8 Participation in exit interview.
11.9 Withdrawal of resignation requires express written approval.
11.10 Management reserves right to relieve early or pay salary in lieu.
11.11 Termination for misconduct without notice in accordance with law.`;

    let c12 = `12.1 Appointment is subject to verification of qualifications and background documents.
12.2 Promptly inform HR in writing of any change in personal/contact details within 7 days.
12.3 Comply with HR Policy and Code of Conduct.
12.4 Company reserves right to amend policies as per operational needs.
12.5 Comply with administrative circulars and orders.
12.6 This Appointment Letter supersedes all prior communications.`;

    let c13 = `You shall strictly adhere to all HR Policies, Code of Conduct, Statutory requirements, and Administrative guidelines.`;
    let c14 = `Please sign and return a copy of this letter to confirm your acceptance of the terms and conditions of employment.`;

    if (force || !frm.doc.introduction || frm.doc.introduction.includes('{')) {
        frm.set_value('introduction', default_intro);
    }
    if (force || !frm.doc.custom_clause_1_appointment_scope) {
        frm.set_value('custom_clause_1_appointment_scope', c1);
    }
    if (force || !frm.doc.custom_clause_2_classification) {
        frm.set_value('custom_clause_2_classification', c2);
    }
    if (force || !frm.doc.custom_clause_3_probation) {
        frm.set_value('custom_clause_3_probation', c3);
    }
    if (force || !frm.doc.custom_clause_4_working_hours) {
        frm.set_value('custom_clause_4_working_hours', c4);
    }
    if (force || !frm.doc.custom_clause_5_leave_policy) {
        frm.set_value('custom_clause_5_leave_policy', c5);
    }
    if (force || !frm.doc.custom_clause_6_compensation) {
        frm.set_value('custom_clause_6_compensation', c6);
    }
    if (force || !frm.doc.custom_clause_7_duties_conduct) {
        frm.set_value('custom_clause_7_duties_conduct', c7);
    }
    if (force || !frm.doc.custom_clause_8_dress_code) {
        frm.set_value('custom_clause_8_dress_code', c8);
    }
    if (force || !frm.doc.custom_clause_9_confidentiality) {
        frm.set_value('custom_clause_9_confidentiality', c9);
    }
    if (force || !frm.doc.custom_clause_10_transfer) {
        frm.set_value('custom_clause_10_transfer', c10);
    }
    if (force || !frm.doc.custom_clause_11_resignation_termination) {
        frm.set_value('custom_clause_11_resignation_termination', c11);
    }
    if (force || !frm.doc.custom_clause_12_general_terms) {
        frm.set_value('custom_clause_12_general_terms', c12);
    }
    if (force || !frm.doc.custom_clause_13_policy_compliance) {
        frm.set_value('custom_clause_13_policy_compliance', c13);
    }
    if (force || !frm.doc.custom_clause_14_acceptance) {
        frm.set_value('custom_clause_14_acceptance', c14);
    }
    if (force || !frm.doc.custom_acceptance_statement) {
        frm.set_value('custom_acceptance_statement', 'I hereby accept the terms and conditions stated in this Appointment Letter.');
    }
}
