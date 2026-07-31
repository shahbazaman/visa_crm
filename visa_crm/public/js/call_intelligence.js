frappe.ui.form.on("Call Intelligence", {

    refresh(frm) {

        if (frm.doc.metadata_status) {
            const color = frm.doc.metadata_status === "Valid" ? "green" : frm.doc.metadata_status === "Waiting" ? "orange" : "red";
            frm.dashboard.add_indicator(__("Metadata: {0}", [frm.doc.metadata_status]), color);
        }
        if (frm.doc.integrity_status) {
            const color = frm.doc.integrity_status === "Mismatch" ? "red" : "green";
            frm.dashboard.add_indicator(__("Integrity: {0}", [frm.doc.integrity_status]), color);
        }

        if (!frm.doc.__islocal) {

            frm.add_custom_button(
                __("Reprocess Audio"),

                function () {

                    frappe.call({

                        method:
"visa_crm.api.gemini_service.retry_processing",

                        args: {
                            name: frm.doc.name
                        },

                        callback() {

                            frappe.show_alert(
                                "Processing started"
                            );

                            frm.reload_doc();

                        }

                    });

                }

            );

        }

    }

});
