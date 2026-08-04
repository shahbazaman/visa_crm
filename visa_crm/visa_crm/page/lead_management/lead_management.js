frappe.pages["lead-management"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Lead Management"), single_column: true });
    new VisaLeadManagement(page);
};

class VisaLeadManagement {
    constructor(page) {
        this.page = page;
        this.state = { category: null, group: null, management: false };
        this.$root = $("<div class='vc-leads'></div>").appendTo(page.main);
        this.add_styles();
        this.add_actions();
        this.show_categories();
    }

    add_actions() {
        this.page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh-cw");
    }

    refresh() {
        if (this.state.group) return this.show_leads(this.state.category, this.state.group);
        if (this.state.category) return this.show_groups(this.state.category);
        return this.show_categories();
    }

    async show_categories() {
        this.state.category = null;
        this.state.group = null;
        this.page.set_title(__("Lead Management"));
        this.loading();
        const data = await this.call("visa_crm.api.lead_management.dashboard");
        this.state.management = Boolean(data.management);
        this.page.clear_inner_toolbar();
        if (this.state.management) {
            this.page.add_inner_button(__("All Leads"), () => frappe.set_route("List", "CRM Lead"));
        }
        const cards = data.categories.map((row) => `
            <button class="vc-category" data-category="${this.escape(row.name)}">
                <span class="vc-category-title">${this.escape(row.category_name)}</span>
                <span class="vc-category-total">${row.total}</span>
                <span class="vc-category-meta">${row.new} new &nbsp; ${row.unassigned} unassigned &nbsp; ${row.overdue} overdue</span>
                <span class="vc-category-meta">${row.needs_attention} need attention &nbsp; ${row.retrying} retrying &nbsp; ${row.failed} failed</span>
                ${row.operational_status === "Future" ? '<span class="vc-badge muted">Coming soon</span>' : ""}
            </button>`).join("");
        const summary = data.summary || {};
        const overview = `<div class="vc-overview">
            <span><strong>${summary.all_leads || 0}</strong>${__("Leads")}</span>
            <span><strong>${summary.unassigned || 0}</strong>${__("Unassigned")}</span>
            <span><strong>${summary.overdue || 0}</strong>${__("Overdue")}</span>
            <span><strong>${summary.needs_attention || 0}</strong>${__("Attention")}</span>
            <span><strong>${summary.retrying || 0}</strong>${__("Retrying")}</span>
            <span><strong>${summary.failed || 0}</strong>${__("Failed")}</span>
        </div>`;
        this.$root.html(`<div class="vc-toolbar"><div><h2>${__("Lead Categories")}</h2><p>${__("Choose a category to see its active groups and leads.")}</p></div>${data.management ? '<button class="btn btn-default btn-sm vc-add-category">' + __("Add Category") + '</button>' : ""}</div>${overview}<div class="vc-category-grid">${cards}</div>`);
        this.$root.find(".vc-category").on("click", (event) => this.show_groups($(event.currentTarget).data("category")));
        this.$root.find(".vc-add-category").on("click", () => this.add_category());
    }

    add_category() {
        const dialog = new frappe.ui.Dialog({
            title: __("Add Lead Category"),
            fields: [
                { fieldname: "category_name", label: __("Category Name"), fieldtype: "Data", reqd: 1 },
                { fieldname: "department", label: __("Responsible Department"), fieldtype: "Link", options: "Department" },
                { fieldname: "sort_order", label: __("Sort Order"), fieldtype: "Int", default: 100 },
                { fieldname: "operational_status", label: __("Operational Status"), fieldtype: "Select", options: "Active\nFuture", default: "Active", reqd: 1 },
                { fieldname: "description", label: __("Description"), fieldtype: "Small Text" },
            ],
            primary_action_label: __("Create"),
            primary_action: async (values) => {
                await this.call("visa_crm.api.lead_management.create_category", values);
                dialog.hide();
                frappe.show_alert({ message: __("Lead category created"), indicator: "green" });
                this.show_categories();
            },
        });
        dialog.show();
    }

    async show_groups(category) {
        this.state.category = category;
        this.state.group = null;
        this.page.set_title(category);
        this.loading();
        const data = await this.call("visa_crm.api.lead_management.groups", { category });
        const rows = data.groups.map((row) => `
            <button class="vc-group" data-group="${this.escape(row.name)}">
                <span><strong>${this.escape(row.name)}</strong><small>${row.new} new &nbsp; ${row.unassigned} unassigned</small></span>
                <span class="vc-group-count">${row.total}</span>
            </button>`).join("");
        this.$root.html(`<div class="vc-toolbar"><button class="btn btn-default btn-sm vc-back">${__("Back")}</button><div class="vc-search-wrap"><input class="form-control vc-search" placeholder="${__("Search all leads in this category")}"><button class="btn btn-primary btn-sm vc-search-button">${__("Search")}</button></div></div><div class="vc-group-list">${rows || '<div class="vc-empty">' + __("No leads in this category") + '</div>'}</div>`);
        this.$root.find(".vc-back").on("click", () => this.show_categories());
        this.$root.find(".vc-group").on("click", (event) => this.show_leads(category, $(event.currentTarget).data("group")));
        this.$root.find(".vc-search-button").on("click", () => this.show_leads(category, null, this.$root.find(".vc-search").val()));
        this.$root.find(".vc-search").on("keydown", (event) => { if (event.key === "Enter") this.show_leads(category, null, event.currentTarget.value); });
    }

    async show_leads(category, group, search) {
        this.state.category = category;
        this.state.group = group;
        this.page.set_title(group || category);
        this.loading();
        const data = await this.call("visa_crm.api.lead_management.leads", { category, group, search });
        const rows = data.rows.map((row) => `
            <div class="vc-lead-row" data-lead="${this.escape(row.name)}">
                <button class="vc-lead-main">
                    <strong>${this.escape(row.lead_name || row.name)}</strong>
                    <span>${this.escape(row.mobile_no || row.phone || "")} ${row.email ? " &nbsp; " + this.escape(row.email) : ""}</span>
                    <small>${this.escape(row.meta_campaign_name || row.source || "")} ${row.visa_type || row.custom_visa_type ? " &nbsp; " + this.escape(row.visa_type || row.custom_visa_type) : ""}</small>
                </button>
                <div class="vc-flags">${this.flags(row)}</div>
                ${this.state.management ? '<button class="btn btn-default btn-xs vc-classify">' + __("Classify") + '</button>' : ""}
            </div>`).join("");
        this.$root.html(`<div class="vc-toolbar"><button class="btn btn-default btn-sm vc-back">${__("Back")}</button><div class="vc-search-wrap"><input class="form-control vc-search" value="${this.escape(search || "")}" placeholder="${__("Name, phone, email, Meta ID, campaign")}"><button class="btn btn-primary btn-sm vc-search-button">${__("Search")}</button></div></div><div class="vc-lead-list">${rows || '<div class="vc-empty">' + __("No matching leads") + '</div>'}</div>`);
        this.$root.find(".vc-back").on("click", () => this.show_groups(category));
        this.$root.find(".vc-lead-main").on("click", (event) => frappe.set_route("Form", "CRM Lead", $(event.currentTarget).closest(".vc-lead-row").data("lead")));
        this.$root.find(".vc-search-button").on("click", () => this.show_leads(category, group, this.$root.find(".vc-search").val()));
        this.$root.find(".vc-search").on("keydown", (event) => { if (event.key === "Enter") this.show_leads(category, group, event.currentTarget.value); });
        this.$root.find(".vc-classify").on("click", (event) => this.classify($(event.currentTarget).closest(".vc-lead-row").data("lead")));
    }

    classify(lead) {
        const dialog = new frappe.ui.Dialog({
            title: __("Move to Category"),
            fields: [
                { fieldname: "category", label: __("Category"), fieldtype: "Link", options: "Lead Category", reqd: 1, get_query: () => ({ filters: { is_active: 1 } }) },
                { fieldname: "group", label: __("Group"), fieldtype: "Data" },
                { fieldname: "reason", label: __("Reason"), fieldtype: "Small Text" },
            ],
            primary_action_label: __("Move"),
            primary_action: async (values) => {
                await this.call("visa_crm.api.lead_management.classify", { lead, ...values });
                dialog.hide();
                frappe.show_alert({ message: __("Lead classification updated"), indicator: "green" });
                this.refresh();
            },
        });
        dialog.show();
    }

    flags(row) {
        const flags = [];
        if (row.is_new) flags.push([__("New"), "blue"]);
        if (row.unassigned) flags.push([__("Unassigned"), "orange"]);
        if (row.overdue_followup) flags.push([__("Overdue"), "red"]);
        if (row.needs_attention) flags.push([__("Needs attention"), "orange"]);
        if (row.retrying) flags.push([__("Retrying"), "blue"]);
        if (row.pipeline_failed) flags.push([__("Pipeline failed"), "red"]);
        return flags.map(([label, color]) => `<span class="vc-badge ${color}">${this.escape(label)}</span>`).join("");
    }

    loading() {
        this.$root.html(`<div class="vc-empty">${__("Loading")}</div>`);
    }

    async call(method, args = {}) {
        const response = await frappe.call({ method, args, freeze: false });
        return response.message || {};
    }

    escape(value) {
        return frappe.utils.escape_html(String(value == null ? "" : value));
    }

    add_styles() {
        if (document.getElementById("vc-lead-management-style")) return;
        $("<style id='vc-lead-management-style'>").text(`
            .vc-leads{padding:20px;max-width:1280px;margin:0 auto}.vc-toolbar{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:18px}.vc-toolbar h2{font-size:20px;margin:0 0 4px}.vc-toolbar p{margin:0;color:var(--text-muted)}.vc-overview{display:grid;grid-template-columns:repeat(6,minmax(90px,1fr));border:1px solid var(--border-color);border-radius:8px;margin-bottom:14px;background:var(--card-bg)}.vc-overview span{padding:10px 12px;color:var(--text-muted);font-size:11px;border-right:1px solid var(--border-color)}.vc-overview span:last-child{border-right:0}.vc-overview strong{display:block;color:var(--text-color);font-size:18px}.vc-category-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.vc-category,.vc-group{background:var(--card-bg);border:1px solid var(--border-color);border-radius:8px;text-align:left;padding:16px;color:var(--text-color)}.vc-category:hover,.vc-group:hover{border-color:var(--gray-500);box-shadow:var(--shadow-sm)}.vc-category-title{display:block;font-size:15px;font-weight:600}.vc-category-total{display:block;font-size:30px;font-weight:650;margin:12px 0}.vc-category-meta{display:block;color:var(--text-muted);font-size:12px;margin-top:4px}.vc-group-list,.vc-lead-list{border:1px solid var(--border-color);border-radius:8px;overflow:hidden;background:var(--card-bg)}.vc-group{display:flex;width:100%;border:0;border-bottom:1px solid var(--border-color);border-radius:0;justify-content:space-between;align-items:center}.vc-group:last-child{border-bottom:0}.vc-group small{display:block;color:var(--text-muted);margin-top:4px}.vc-group-count{font-size:18px;font-weight:600}.vc-search-wrap{display:flex;gap:8px;min-width:min(520px,70vw)}.vc-lead-row{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:12px;align-items:center;padding:12px 14px;border-bottom:1px solid var(--border-color)}.vc-lead-row:last-child{border-bottom:0}.vc-lead-main{border:0;background:none;text-align:left;min-width:0;color:var(--text-color)}.vc-lead-main strong,.vc-lead-main span,.vc-lead-main small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.vc-lead-main span,.vc-lead-main small{color:var(--text-muted);margin-top:3px}.vc-flags{display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end}.vc-badge{display:inline-flex;border-radius:999px;padding:2px 7px;font-size:11px;background:var(--gray-100);color:var(--gray-700)}.vc-badge.blue{background:var(--blue-100);color:var(--blue-700)}.vc-badge.orange{background:var(--orange-100);color:var(--orange-700)}.vc-badge.red{background:var(--red-100);color:var(--red-700)}.vc-badge.muted{margin-top:10px}.vc-empty{padding:42px;text-align:center;color:var(--text-muted)}@media(max-width:700px){.vc-leads{padding:12px}.vc-toolbar{align-items:stretch;flex-direction:column}.vc-overview{grid-template-columns:repeat(2,minmax(0,1fr))}.vc-overview span{border-bottom:1px solid var(--border-color)}.vc-search-wrap{min-width:0;width:100%}.vc-lead-row{grid-template-columns:minmax(0,1fr) auto}.vc-flags{grid-column:1/-1;justify-content:flex-start}}
        `).appendTo(document.head);
    }
}
