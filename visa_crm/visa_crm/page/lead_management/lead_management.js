/**
 * Lead Management Desk Page — 3-Page Hierarchical Navigation
 *
 * Page State URL Encoding:
 *   Page 1 (Categories):    /app/lead-management
 *   Page 2 (Subcategories): /app/lead-management?category=<encodedCategory>
 *   Page 3 (Leads):        /app/lead-management?category=<encodedCategory>&subcategory=<encodedSubcategory>
 *   Page 4 (Lead Detail):  /crm/leads/<name>#activity (native CRM SPA)
 *
 * Uses URL query parameters so Frappe Desk router resolves the page as 'lead-management'
 * without triggering 'Page category not found' or broken website routes.
 */

frappe.pages["lead-management"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("Lead Management"),
        single_column: true
    });
    const mgr = new VisaLeadManagement(page, wrapper);
    wrapper._visa_lead_mgr = mgr;
};

frappe.pages["lead-management"].on_page_show = function (wrapper) {
    const mgr = wrapper._visa_lead_mgr;
    if (mgr) mgr.handle_route();
};

window.VisaLeadManagement = class VisaLeadManagement {
    constructor(page, wrapper) {
        this.page = page;
        this.wrapper = wrapper;
        this._inject_styles();
        this.$root = $('<div class="vlm-root"></div>').appendTo(page.body);

        // Cache for API responses to keep back navigation instant
        this._cat_cache = null;
        this._sub_cache = {};   // key: category
        this._lead_cache = {};  // key: "cat::sub"

        // Listen for popstate (browser Back / Forward buttons)
        this._onpopstate = () => this.handle_route();
        window.addEventListener("popstate", this._onpopstate);

        this.handle_route();
    }

    /* ─── Helper: Get URL Search Parameters ──────────────────────── */
    _get_params() {
        const search = window.location.search || "";
        const urlParams = new URLSearchParams(search);

        // Also fallback to frappe.route_options if available
        let category = urlParams.get("category") || (frappe.route_options && frappe.route_options.category) || null;
        let subcategory = urlParams.get("subcategory") || (frappe.route_options && frappe.route_options.subcategory) || null;

        return { category, subcategory };
    }

    /* ─── Helper: Navigate to URL State ─────────────────────────── */
    _navigate(category, subcategory) {
        let path = "/app/lead-management";
        const params = new URLSearchParams();
        if (category) params.set("category", category);
        if (subcategory) params.set("subcategory", subcategory);

        const queryString = params.toString();
        const fullUrl = path + (queryString ? "?" + queryString : "");

        window.history.pushState({ category, subcategory }, "", fullUrl);
        if (frappe.route_options) {
            frappe.route_options.category = category;
            frappe.route_options.subcategory = subcategory;
        }
        this.handle_route();
    }

    /* ─── Router Dispatcher ─────────────────────────────────────── */
    handle_route() {
        const { category, subcategory } = this._get_params();

        if (category && subcategory) {
            this._show_leads(category, subcategory);
        } else if (category) {
            this._show_subcategories(category);
        } else {
            this._show_categories();
        }
    }

    /* ─── PAGE 1: Categories ────────────────────────────────────── */
    async _show_categories() {
        this.page.set_title(__("Lead Management"));
        this.page.clear_primary_action();
        this.page.clear_secondary_action();
        this.page.set_primary_action(__("New Lead"), () => frappe.new_doc("CRM Lead"), "add");

        this.$root.html(_tpl_loading(__("Loading categories...")));

        try {
            if (!this._cat_cache) {
                const res = await frappe.call({
                    method: "visa_crm.api.lead_tree.get_lead_tree_nodes",
                    args: { parent_level: "Categories" }
                });
                this._cat_cache = (res.message || []);
            }
            this._render_categories(this._cat_cache);
        } catch (e) {
            this._render_error(__("Failed to load categories"), e.message, () => {
                this._cat_cache = null;
                this._show_categories();
            });
        }
    }

    _render_categories(cats) {
        if (!cats || cats.length === 0) {
            this.$root.html(_tpl_empty(
                __("No lead categories found."),
                __("Leads arriving from Meta will appear here once ingested.")
            ));
            return;
        }

        let html = `
            <div class="vlm-page">
                <div class="vlm-page-header">
                    <h2 class="vlm-page-title">${__("Categories")}</h2>
                    <p class="vlm-page-subtitle">${__("Select a category to view subcategories.")}</p>
                </div>
                <div class="vlm-grid">`;

        for (const cat of cats) {
            const catValue = cat.value;
            const catLabel = frappe.utils.escape_html(cat.label);
            const count = cat.count || 0;

            html += `
                <div class="vlm-card" data-cat="${frappe.utils.escape_html(catValue)}" tabindex="0" role="button"
                     aria-label="${catLabel}: ${count} leads">
                    <div class="vlm-card-icon">
                        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/>
                        </svg>
                    </div>
                    <div class="vlm-card-body">
                        <div class="vlm-card-title">${catLabel}</div>
                        <div class="vlm-card-count">${count} ${__(count === 1 ? "lead" : "leads")}</div>
                    </div>
                    <div class="vlm-card-arrow">›</div>
                </div>`;
        }

        html += `</div></div>`;
        this.$root.html(html);

        const self = this;
        this.$root.find(".vlm-card").on("click keydown", function (e) {
            if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
            const cat = $(this).attr("data-cat");
            if (cat) self._navigate(cat, null);
        });
    }

    /* ─── PAGE 2: Subcategories ─────────────────────────────────── */
    async _show_subcategories(category) {
        const title = frappe.utils.escape_html(category);
        this.page.set_title(__("Lead Management") + " — " + title);
        this.page.clear_primary_action();
        this.page.clear_secondary_action();
        this.page.set_secondary_action(__("← Back"), () => {
            this._navigate(null, null);
        }, "left");

        this.$root.html(_tpl_loading(__("Loading subcategories...")));

        try {
            if (!this._sub_cache[category]) {
                const res = await frappe.call({
                    method: "visa_crm.api.lead_tree.get_lead_tree_nodes",
                    args: { parent_level: "Subcategories", category }
                });
                this._sub_cache[category] = (res.message || []);
            }
            this._render_subcategories(category, this._sub_cache[category]);
        } catch (e) {
            this._render_error(__("Failed to load subcategories"), e.message, () => {
                delete this._sub_cache[category];
                this._show_subcategories(category);
            });
        }
    }

    _render_subcategories(category, subs) {
        const escapedCat = frappe.utils.escape_html(category);

        let html = `
            <div class="vlm-page">
                <div class="vlm-breadcrumb">
                    <a href="javascript:void(0)" class="vlm-breadcrumb-link vlm-back-root">${__("Lead Management")}</a>
                    <span class="vlm-breadcrumb-sep">›</span>
                    <span class="vlm-breadcrumb-current">${escapedCat}</span>
                </div>
                <div class="vlm-page-header">
                    <h2 class="vlm-page-title">${escapedCat}</h2>
                    <p class="vlm-page-subtitle">${__("Select a subcategory to view leads.")}</p>
                </div>`;

        if (!subs || subs.length === 0) {
            html += _tpl_empty(__("No subcategories found."), __("No leads in this category yet."));
        } else {
            html += '<div class="vlm-grid">';
            for (const sub of subs) {
                const subValue = sub.value;
                const subLabel = frappe.utils.escape_html(sub.label);
                const count = sub.count || 0;

                html += `
                    <div class="vlm-card vlm-card-sub" data-cat="${frappe.utils.escape_html(category)}" data-sub="${frappe.utils.escape_html(subValue)}" tabindex="0" role="button"
                         aria-label="${subLabel}: ${count} leads">
                        <div class="vlm-card-icon vlm-icon-sub">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M4 6h16M4 10h16M4 14h8M4 18h8"/>
                            </svg>
                        </div>
                        <div class="vlm-card-body">
                            <div class="vlm-card-title">${subLabel}</div>
                            <div class="vlm-card-count">${count} ${__(count === 1 ? "lead" : "leads")}</div>
                        </div>
                        <div class="vlm-card-arrow">›</div>
                    </div>`;
            }
            html += '</div>';
        }

        html += `</div>`;
        this.$root.html(html);

        const self = this;
        this.$root.find(".vlm-back-root").on("click", (e) => {
            e.preventDefault();
            self._navigate(null, null);
        });
        this.$root.find(".vlm-card").on("click keydown", function (e) {
            if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
            const cat = $(this).attr("data-cat");
            const sub = $(this).attr("data-sub");
            if (cat && sub) self._navigate(cat, sub);
        });
    }

    /* ─── PAGE 3: Leads ─────────────────────────────────────────── */
    _get_lead_state(category, subcategory) {
        const key = category + "::" + subcategory;
        if (!this._lead_cache[key]) {
            this._lead_cache[key] = {
                data: [],
                has_more: false,
                page: 1,
                search: "",
                status: "",
                loading: false,
                loaded: false,
                error: null
            };
        }
        return this._lead_cache[key];
    }

    _show_leads(category, subcategory) {
        const escapedCat = frappe.utils.escape_html(category);
        const escapedSub = frappe.utils.escape_html(subcategory);

        this.page.set_title(escapedCat + " / " + escapedSub);
        this.page.clear_primary_action();
        this.page.clear_secondary_action();
        this.page.set_secondary_action(__("← Back"), () => {
            this._navigate(category, null);
        }, "left");

        const state = this._get_lead_state(category, subcategory);
        this._render_lead_page(category, subcategory, state);

        if (!state.loaded && !state.loading) {
            this._fetch_leads(category, subcategory, 1);
        }
    }

    _render_lead_page(category, subcategory, state) {
        const escapedCat = frappe.utils.escape_html(category);
        const escapedSub = frappe.utils.escape_html(subcategory);

        const html = `
            <div class="vlm-page vlm-leads-page">
                <div class="vlm-breadcrumb">
                    <a href="javascript:void(0)" class="vlm-breadcrumb-link vlm-back-root">${__("Lead Management")}</a>
                    <span class="vlm-breadcrumb-sep">›</span>
                    <a href="javascript:void(0)" class="vlm-breadcrumb-link vlm-back-cat">${escapedCat}</a>
                    <span class="vlm-breadcrumb-sep">›</span>
                    <span class="vlm-breadcrumb-current">${escapedSub}</span>
                </div>
                <div class="vlm-page-header vlm-lead-header">
                    <div>
                        <h2 class="vlm-page-title">${escapedSub}</h2>
                        <p class="vlm-page-subtitle vlm-lead-subtitle">${escapedCat}</p>
                    </div>
                    <div class="vlm-lead-toolbar">
                        <input type="text" class="form-control input-sm vlm-search"
                               placeholder="${__("Search name, phone, email...")}"
                               value="${frappe.utils.escape_html(state.search)}" />
                        <select class="form-control input-sm vlm-status-filter">
                            <option value="">${__("All Statuses")}</option>
                            <option value="New"${state.status === "New" ? " selected" : ""}>${__("New")}</option>
                            <option value="Open"${state.status === "Open" ? " selected" : ""}>${__("Open")}</option>
                            <option value="Lead Qualified"${state.status === "Lead Qualified" ? " selected" : ""}>${__("Lead Qualified")}</option>
                            <option value="Contacted"${state.status === "Contacted" ? " selected" : ""}>${__("Contacted")}</option>
                            <option value="Interested"${state.status === "Interested" ? " selected" : ""}>${__("Interested")}</option>
                            <option value="Closed"${state.status === "Closed" ? " selected" : ""}>${__("Closed")}</option>
                            <option value="Lost"${state.status === "Lost" ? " selected" : ""}>${__("Lost")}</option>
                        </select>
                        <select class="form-control input-sm vlm-classification-filter">
                            <option value="All"${state.classification_filter === "All" || !state.classification_filter ? " selected" : ""}>${__("All Classifications")}</option>
                            <option value="Categorized"${state.classification_filter === "Categorized" ? " selected" : ""}>${__("Categorized")}</option>
                            <option value="Uncategorized"${state.classification_filter === "Uncategorized" ? " selected" : ""}>${__("Uncategorized")}</option>
                            <option value="Manual"${state.classification_filter === "Manual" ? " selected" : ""}>${__("Manually Classified")}</option>
                            <option value="Automatic"${state.classification_filter === "Automatic" ? " selected" : ""}>${__("Automatically Classified")}</option>
                        </select>
                        <button class="btn btn-primary btn-sm vlm-btn-bulk-assign" style="display:none;">${__("Assign Category")}</button>
                        <button class="btn btn-default btn-sm vlm-btn-clear">${__("Clear")}</button>
                    </div>
                </div>
                <div class="vlm-lead-content" id="vlm-lead-content"></div>
            </div>`;

        this.$root.html(html);

        const self = this;
        // Bind breadcrumb links
        this.$root.find(".vlm-back-root").on("click", (e) => {
            e.preventDefault();
            self._navigate(null, null);
        });
        this.$root.find(".vlm-back-cat").on("click", (e) => {
            e.preventDefault();
            self._navigate(category, null);
        });

        // Search with debounce
        let _searchTimer = null;
        this.$root.find(".vlm-search").on("input", (e) => {
            clearTimeout(_searchTimer);
            _searchTimer = setTimeout(() => {
                const s = self._get_lead_state(category, subcategory);
                s.search = $(e.target).val().trim();
                s.data = [];
                s.page = 1;
                s.loaded = false;
                self._fetch_leads(category, subcategory, 1);
            }, 300);
        });

        // Status filter
        this.$root.find(".vlm-status-filter").on("change", (e) => {
            const s = self._get_lead_state(category, subcategory);
            s.status = $(e.target).val();
            s.data = [];
            s.page = 1;
            s.loaded = false;
            self._fetch_leads(category, subcategory, 1);
        });

        // Classification filter
        this.$root.find(".vlm-classification-filter").on("change", (e) => {
            const s = self._get_lead_state(category, subcategory);
            s.classification_filter = $(e.target).val();
            s.data = [];
            s.page = 1;
            s.loaded = false;
            self._fetch_leads(category, subcategory, 1);
        });

        // Bulk assign button
        this.$root.find(".vlm-btn-bulk-assign").on("click", () => {
            const selected = [];
            self.$root.find(".vlm-row-check:checked").each(function () {
                selected.push($(this).val());
            });
            if (selected.length) {
                self._open_assign_category_dialog(selected);
            }
        });

        // Clear filters
        this.$root.find(".vlm-btn-clear").on("click", () => {
            const s = self._get_lead_state(category, subcategory);
            s.search = "";
            s.status = "";
            s.classification_filter = "All";
            s.data = [];
            s.page = 1;
            s.loaded = false;
            self.$root.find(".vlm-search").val("");
            self.$root.find(".vlm-status-filter").val("");
            self.$root.find(".vlm-classification-filter").val("All");
            self._fetch_leads(category, subcategory, 1);
        });

        this._render_lead_list(category, subcategory, state);
    }

    async _fetch_leads(category, subcategory, page) {
        const state = this._get_lead_state(category, subcategory);
        state.loading = true;
        state.error = null;
        this._render_lead_list(category, subcategory, state);

        try {
            const filtersObj = {};
            if (state.search) filtersObj.search = state.search;
            if (state.status) filtersObj.status = [state.status];
            if (state.classification_filter) filtersObj.classification_filter = state.classification_filter;
            filtersObj.page = page;
            filtersObj.page_length = 20;

            const res = await frappe.call({
                method: "visa_crm.api.lead_tree.get_lead_tree_nodes",
                args: {
                    parent_level: "Leads",
                    category,
                    subcategory,
                    filters: JSON.stringify(filtersObj)
                }
            });
            const result = res.message || { data: [], has_more: false, page: 1 };
            if (page === 1) {
                state.data = result.data || [];
            } else {
                state.data = state.data.concat(result.data || []);
            }
            state.has_more = !!result.has_more;
            state.page = page;
            state.loaded = true;
        } catch (e) {
            state.error = e.message || __("Failed to load leads");
        } finally {
            state.loading = false;
            this._render_lead_list(category, subcategory, state);
        }
    }

    _render_lead_list(category, subcategory, state) {
        const $content = this.$root.find("#vlm-lead-content");
        if (!$content.length) return;

        if (state.loading && state.data.length === 0) {
            $content.html(_tpl_loading(__("Loading leads...")));
            return;
        }
        if (state.error) {
            $content.html(_tpl_error_inline(state.error, () => {
                state.data = [];
                state.loaded = false;
                this._fetch_leads(category, subcategory, 1);
            }));
            return;
        }
        if (!state.loading && state.data.length === 0) {
            $content.html(_tpl_empty(
                __("No leads found."),
                state.search || state.status || state.classification_filter
                    ? __("No leads match the current filters.")
                    : __("This subcategory has no leads yet.")
            ));
            return;
        }

        let html = `
            <div class="vlm-lead-table-wrap">
                <div class="vlm-lead-table-header">
                    <div style="width:32px;"><input type="checkbox" class="vlm-select-all" /></div>
                    <div class="vlm-th vlm-th-name">${__("Lead")}</div>
                    <div class="vlm-th vlm-th-status">${__("Status")}</div>
                    <div class="vlm-th vlm-th-contact">${__("Contact")}</div>
                    <div class="vlm-th vlm-th-owner">${__("Owner")}</div>
                    <div class="vlm-th vlm-th-date">${__("Modified")}</div>
                    <div style="width:110px;text-align:right;">${__("Actions")}</div>
                </div>`;

        for (const lead of state.data) {
            const name = frappe.utils.escape_html(lead.lead_name || lead.first_name || lead.name);
            const id = frappe.utils.escape_html(lead.name);
            const status = frappe.utils.escape_html(lead.status || "Open");
            const owner = frappe.utils.escape_html(lead.lead_owner || __("Unassigned"));
            const phone = frappe.utils.escape_html(lead.mobile_no || "");
            const email = frappe.utils.escape_html(lead.email || "");
            const modified = lead.modified
                ? frappe.datetime.prettyDate(lead.modified)
                : "";
            const statusClass = _status_class(status);

            html += `
                <div class="vlm-lead-row" data-lead="${id}" tabindex="0" role="button">
                    <div style="width:32px;" onclick="event.stopPropagation();">
                        <input type="checkbox" class="vlm-row-check" value="${id}" />
                    </div>
                    <div class="vlm-td vlm-td-name">
                        <div class="vlm-lead-name">${name}</div>
                        <div class="vlm-lead-id">${id}</div>
                    </div>
                    <div class="vlm-td vlm-td-status">
                        <span class="vlm-status-badge ${statusClass}">${status}</span>
                    </div>
                    <div class="vlm-td vlm-td-contact">
                        ${phone ? `<div class="vlm-contact-line">📞 ${phone}</div>` : ""}
                        ${email ? `<div class="vlm-contact-line vlm-email">✉ ${email}</div>` : ""}
                        ${!phone && !email ? `<span class="text-muted">—</span>` : ""}
                    </div>
                    <div class="vlm-td vlm-td-owner">
                        <span class="vlm-owner-name">${owner}</span>
                    </div>
                    <div class="vlm-td vlm-td-date text-muted">${modified}</div>
                    <div style="width:110px;text-align:right;" onclick="event.stopPropagation();">
                        <button class="btn btn-default btn-xs vlm-btn-assign-row" data-lead="${id}">${__("Categorize")}</button>
                    </div>
                </div>`;
        }

        html += `</div>`;

        if (state.has_more) {
            html += `
                <div class="vlm-load-more-wrap">
                    <button class="btn btn-default btn-sm vlm-btn-load-more"
                            ${state.loading ? "disabled" : ""}>
                        ${state.loading ? __("Loading...") : __("Load More Leads")}
                    </button>
                </div>`;
        }

        $content.html(html);

        const self = this;
        // Checkboxes & Bulk Actions
        $content.find(".vlm-select-all").on("change", function () {
            const checked = $(this).prop("checked");
            $content.find(".vlm-row-check").prop("checked", checked);
            self._update_bulk_btn();
        });

        $content.find(".vlm-row-check").on("change", function () {
            self._update_bulk_btn();
        });

        // Row Assign Category Button
        $content.find(".vlm-btn-assign-row").on("click", function (e) {
            e.stopPropagation();
            const leadId = $(this).data("lead");
            if (leadId) self._open_assign_category_dialog([leadId]);
        });

        // Click lead row → Navigate to native CRM Lead detail UI: /crm/leads/<name>#activity
        $content.find(".vlm-lead-row").on("click keydown", function (e) {
            if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
            if ($(e.target).is("input, button, a")) return;
            const leadId = $(this).data("lead");
            if (leadId) {
                window.location.href = "/crm/leads/" + encodeURIComponent(leadId) + "#activity";
            }
        });

        // Load more
        $content.find(".vlm-btn-load-more").on("click", () => {
            if (!state.loading && state.has_more) {
                self._fetch_leads(category, subcategory, state.page + 1);
            }
        });
    }

    _update_bulk_btn() {
        const checkedCount = this.$root.find(".vlm-row-check:checked").length;
        const $btn = this.$root.find(".vlm-btn-bulk-assign");
        if (checkedCount > 0) {
            $btn.text(__("Assign Category ({0})", [checkedCount])).show();
        } else {
            $btn.hide();
        }
    }

    _open_assign_category_dialog(leadIds) {
        const self = this;
        const isBulk = Array.isArray(leadIds) && leadIds.length > 1;

        frappe.call({
            method: "visa_crm.api.lead_management.subcategories",
            callback: function (r) {
                const res = r.message || {};
                const categories = res.categories || [];
                const catNames = categories.map(c => c.name);

                const dialog = new frappe.ui.Dialog({
                    title: isBulk ? __("Bulk Assign Category ({0} leads)", [leadIds.length]) : __("Assign Lead Category"),
                    fields: [
                        {
                            fieldname: "category",
                            fieldtype: "Select",
                            label: __("Category"),
                            options: catNames.join("\n"),
                            reqd: 1,
                            onchange: function () {
                                const selectedCat = dialog.get_value("category");
                                frappe.call({
                                    method: "visa_crm.api.lead_management.subcategories",
                                    args: { category: selectedCat },
                                    callback: function (subRes) {
                                        const subs = (subRes.message || {}).subcategories || [];
                                        dialog.set_df_property("group", "options", ["Unspecified"].concat(subs).join("\n"));
                                    }
                                });
                            }
                        },
                        {
                            fieldname: "group",
                            fieldtype: "Select",
                            label: __("Subcategory"),
                            options: "Unspecified",
                        },
                        {
                            fieldname: "reason",
                            fieldtype: "Small Text",
                            label: __("Classification Reason / Note"),
                            default: "Manual category assignment by management"
                        }
                    ],
                    primary_action_label: __("Save Category"),
                    primary_action: function (values) {
                        dialog.hide();
                        if (isBulk) {
                            frappe.call({
                                method: "visa_crm.api.lead_management.bulk_classify",
                                args: {
                                    leads: leadIds,
                                    category: values.category,
                                    group: values.group,
                                    reason: values.reason
                                },
                                callback: function (res) {
                                    if (res.message && res.message.ok) {
                                        frappe.show_alert({ message: __("Successfully categorized {0} leads", [res.message.total]), indicator: "green" });
                                    } else {
                                        frappe.show_alert({ message: __("Categorized {0} leads ({1} failed)", [(res.message.succeeded || []).length, (res.message.failed || []).length]), indicator: "orange" });
                                    }
                                    self._cat_cache = null;
                                    self._sub_cache = {};
                                    self.handle_route();
                                }
                            });
                        } else {
                            const singleId = Array.isArray(leadIds) ? leadIds[0] : leadIds;
                            frappe.call({
                                method: "visa_crm.api.lead_management.classify",
                                args: {
                                    lead: singleId,
                                    category: values.category,
                                    group: values.group,
                                    reason: values.reason
                                },
                                callback: function () {
                                    frappe.show_alert({ message: __("Lead category updated successfully"), indicator: "green" });
                                    self._cat_cache = null;
                                    self._sub_cache = {};
                                    self.handle_route();
                                }
                            });
                        }
                    }
                });
                dialog.show();
            }
        });
    }

    /* ─── Error rendering ───────────────────────────────────────── */
    _render_error(title, detail, retryFn) {
        this.$root.html(`
            <div class="vlm-page">
                <div class="vlm-state vlm-state-error">
                    <div class="vlm-state-icon">⚠</div>
                    <div class="vlm-state-title">${frappe.utils.escape_html(title)}</div>
                    <div class="vlm-state-detail">${frappe.utils.escape_html(detail || "")}</div>
                    <button class="btn btn-default btn-sm vlm-btn-retry" style="margin-top:12px;">
                        ${__("Retry")}
                    </button>
                </div>
            </div>`);
        this.$root.find(".vlm-btn-retry").on("click", retryFn);
    }

    /* ─── Inject Component CSS ──────────────────────────────────── */
    _inject_styles() {
        if (document.getElementById("vlm-styles")) return;
        const s = document.createElement("style");
        s.id = "vlm-styles";
        s.textContent = `
.vlm-root { padding: 20px; max-width: 1100px; margin: 0 auto; font-family: var(--font-stack, system-ui, sans-serif); }
.vlm-breadcrumb { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-muted, #8d99a6); margin-bottom: 12px; }
.vlm-breadcrumb-link { color: var(--text-muted, #8d99a6); text-decoration: none; cursor: pointer; }
.vlm-breadcrumb-link:hover { color: var(--text-color, #2d3748); text-decoration: underline; }
.vlm-breadcrumb-sep { opacity: 0.5; }
.vlm-breadcrumb-current { color: var(--text-color, #1a202c); font-weight: 500; }
.vlm-page-header { margin-bottom: 20px; }
.vlm-page-title { font-size: 22px; font-weight: 700; margin: 0 0 4px; color: var(--heading-color, #1a202c); }
.vlm-page-subtitle { font-size: 13px; color: var(--text-muted, #8d99a6); margin: 0; }
.vlm-grid { display: flex; flex-direction: column; gap: 8px; }
.vlm-card {
    display: flex; align-items: center; gap: 14px;
    padding: 14px 18px; border-radius: 8px;
    border: 1px solid var(--border-color, #e2e8f0);
    background: var(--card-bg, #fff);
    cursor: pointer; user-select: none;
    transition: box-shadow 0.15s ease, border-color 0.15s ease;
}
.vlm-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-color: var(--primary, #3182ce); }
.vlm-card:focus { outline: 2px solid var(--primary, #3182ce); outline-offset: 1px; }
.vlm-card-icon { color: var(--primary, #3182ce); flex-shrink: 0; }
.vlm-card-sub .vlm-card-icon { color: #805ad5; }
.vlm-card-body { flex: 1; }
.vlm-card-title { font-size: 15px; font-weight: 600; color: var(--text-color, #1a202c); }
.vlm-card-count { font-size: 12px; color: var(--text-muted, #718096); margin-top: 2px; }
.vlm-card-arrow { font-size: 20px; color: var(--text-muted, #a0aec0); }
.vlm-lead-header { display: flex; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
.vlm-lead-toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.vlm-search { width: 220px; }
.vlm-status-filter { width: 150px; }
.vlm-lead-subtitle { font-size: 12px; color: var(--text-muted, #718096); }
.vlm-lead-table-wrap { border: 1px solid var(--border-color, #e2e8f0); border-radius: 8px; overflow: hidden; }
.vlm-lead-table-header {
    display: flex; padding: 10px 16px;
    background: var(--control-bg, #f4f5f7);
    border-bottom: 1px solid var(--border-color, #e2e8f0);
    font-size: 11px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.04em; color: var(--text-muted, #718096);
}
.vlm-lead-row {
    display: flex; align-items: center; padding: 12px 16px;
    border-bottom: 1px solid var(--border-color, #edf2f7);
    cursor: pointer; transition: background 0.12s ease; font-size: 13px;
}
.vlm-lead-row:last-child { border-bottom: none; }
.vlm-lead-row:hover { background: var(--hover-bg, #f7fafc); }
.vlm-lead-row:focus { outline: 2px solid var(--primary, #3182ce); outline-offset: -2px; }
.vlm-th, .vlm-td { padding: 0 6px; overflow: hidden; text-overflow: ellipsis; }
.vlm-th-name, .vlm-td-name   { flex: 2.5; min-width: 140px; }
.vlm-th-status, .vlm-td-status { width: 130px; }
.vlm-th-contact, .vlm-td-contact { flex: 2; min-width: 130px; }
.vlm-th-owner, .vlm-td-owner  { flex: 1.5; min-width: 100px; }
.vlm-th-date, .vlm-td-date    { width: 100px; text-align: right; font-size: 11px; flex-shrink: 0; }
.vlm-lead-name { font-weight: 600; color: var(--text-color, #1a202c); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.vlm-lead-id   { font-size: 10px; color: var(--text-muted, #a0aec0); white-space: nowrap; }
.vlm-contact-line { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.5; }
.vlm-email { color: var(--text-muted, #718096); font-size: 11px; }
.vlm-owner-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.vlm-status-badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; white-space: nowrap; }
.vlm-badge-qualified { background: #c6f6d5; color: #276749; }
.vlm-badge-new, .vlm-badge-open { background: #bee3f8; color: #2a69ac; }
.vlm-badge-contacted, .vlm-badge-interested { background: #fefcbf; color: #975a16; }
.vlm-badge-closed { background: #e9d8fd; color: #553c9a; }
.vlm-badge-lost { background: #fed7d7; color: #9b2c2c; }
.vlm-badge-default { background: #edf2f7; color: #4a5568; }
.vlm-load-more-wrap { padding: 14px; text-align: center; }
.vlm-state { text-align: center; padding: 60px 20px; }
.vlm-state-icon { font-size: 40px; margin-bottom: 12px; opacity: 0.5; }
.vlm-state-title { font-size: 16px; font-weight: 600; margin-bottom: 6px; }
.vlm-state-detail { font-size: 13px; color: var(--text-muted, #718096); }
.vlm-state-error .vlm-state-icon { color: var(--danger, #e53e3e); opacity: 1; }
.vlm-state-error .vlm-state-title { color: var(--danger, #e53e3e); }
.vlm-error-inline { padding: 16px; background: #fff5f5; border-radius: 6px; border: 1px solid #fed7d7; color: #9b2c2c; font-size: 13px; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.vlm-spinner { display: inline-block; width: 28px; height: 28px; border: 3px solid rgba(0,0,0,0.1); border-top-color: var(--primary, #3182ce); border-radius: 50%; animation: vlm-spin 0.8s linear infinite; margin-bottom: 10px; }
@keyframes vlm-spin { to { transform: rotate(360deg); } }
`;
        document.head.appendChild(s);
    }
};

/* ─── Render Helper Templates ───────────────────────────────────── */
function _tpl_loading(msg) {
    return `<div class="vlm-state">
        <div class="vlm-spinner"></div>
        <div class="vlm-state-title">${frappe.utils.escape_html(msg)}</div>
    </div>`;
}

function _tpl_empty(title, detail) {
    return `<div class="vlm-state">
        <div class="vlm-state-icon">📭</div>
        <div class="vlm-state-title">${frappe.utils.escape_html(title)}</div>
        <div class="vlm-state-detail">${frappe.utils.escape_html(detail || "")}</div>
    </div>`;
}

function _tpl_error_inline(msg, retryFn) {
    const el = $(`<div class="vlm-error-inline">
        <span>⚠ ${frappe.utils.escape_html(msg || __("An error occurred"))}</span>
        <button class="btn btn-default btn-xs">${__("Retry")}</button>
    </div>`);
    el.find("button").on("click", retryFn);
    return el;
}

function _status_class(status) {
    const s = (status || "").toLowerCase().replace(/\s+/g, "-");
    const map = {
        "lead-qualified": "vlm-badge-qualified",
        "new": "vlm-badge-new",
        "open": "vlm-badge-open",
        "contacted": "vlm-badge-contacted",
        "interested": "vlm-badge-interested",
        "closed": "vlm-badge-closed",
        "lost": "vlm-badge-lost"
    };
    return map[s] || "vlm-badge-default";
}
