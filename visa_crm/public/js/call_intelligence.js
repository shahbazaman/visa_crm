frappe.ui.form.on("Call Intelligence", {

    refresh(frm) {

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
