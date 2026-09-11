// Employee Desk Customizations for Visa CRM
frappe.ui.form.on('Employee', {
    refresh: function(frm) {
        // Aadhaar and PAN formatting
        if (frm.doc.custom_aadhaar_number) {
            frm.set_df_property('custom_aadhaar_number', 'description', '12-digit Indian Unique Identification Number');
        }
    },
    custom_aadhaar_number: function(frm) {
        if (frm.doc.custom_aadhaar_number) {
            let val = frm.doc.custom_aadhaar_number.replace(/\D/g, '');
            if (val.length === 12) {
                frm.set_value('custom_aadhaar_number', val.replace(/(\d{4})(\d{4})(\d{4})/, '$1-$2-$3'));
            } else if (val.length > 0 && val.length !== 12) {
                frappe.msgprint(__('Aadhaar number must be exactly 12 digits'));
            }
        }
    },
    pan_number: function(frm) {
        if (frm.doc.pan_number) {
            let pan = frm.doc.pan_number.toUpperCase().trim();
            frm.set_value('pan_number', pan);
            let panRegex = /^[A-Z]{5}[0-9]{4}[A-Z]{1}$/;
            if (!panRegex.test(pan)) {
                frappe.msgprint(__('Invalid PAN format. Standard format: ABCDE1234F'));
            }
        }
    }
});
