frappe.ui.form.on('Appointment Letter', {
    refresh: function(frm) {
        if (!frm.is_new()) {
            let isHolidays = (frm.doc.company || '').toLowerCase().includes('holiday') ||
                             (frm.doc.appointment_letter_template || '').toLowerCase().includes('holiday');
            let defaultFormat = isHolidays ? 'Middle East Holidays Appointment Letter' : 'Middle East Travels Appointment Letter';

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
    }
});
