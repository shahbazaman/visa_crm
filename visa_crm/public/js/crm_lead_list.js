frappe.listview_settings["CRM Lead"] = {
    onload(listview) {
        listview.page.add_inner_button(__("Category View"), () => frappe.set_route("lead-management"));
    },
};
