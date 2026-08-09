frappe.pages["lead-management"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Lead Management"), single_column: true });
    const treePageClass = window.VisaLeadTreePage || VisaLeadTreePage;
    new treePageClass(page);
};

window.VisaLeadTreePage = class VisaLeadTreePage {
    constructor(page) {
        this.page = page;
        this.filters = { search: "", status: "" };
        this.categories = [];
        this.subcategories = {}; // key: category_name -> Array of subcategory nodes
        this.leads = {}; // key: "category_name::subcategory_name" -> { data: [], page: 1, has_more: false }
        this.expandedCategories = new Set();
        this.expandedSubcategories = new Set();
        this.loading = { categories: false, subcategories: {}, leads: {} };
        this.errors = { categories: null, subcategories: {}, leads: {} };

        this.setup_ui();
        this.load_categories();
    }

    setup_ui() {
        this.page.set_primary_action(__("New Lead"), () => frappe.new_doc("CRM Lead"), "add");
        this.page.set_secondary_action(__("Refresh"), () => this.load_categories(), "refresh");

        this.$root = $('<div class="vc-lead-tree-page"></div>').appendTo(this.page.body);
        this.inject_styles();

        const toolbarHtml = `
            <div class="vc-tree-toolbar">
                <div class="vc-search-box">
                    <input type="text" class="form-control input-sm vc-input-search" placeholder="${__("Search leads by name, email, phone...")}" />
                </div>
                <div class="vc-filter-box">
                    <select class="form-control input-sm vc-select-status">
                        <option value="">${__("All Statuses")}</option>
                        <option value="Lead Qualified">${__("Lead Qualified")}</option>
                        <option value="New">${__("New")}</option>
                        <option value="Open">${__("Open")}</option>
                        <option value="Contacted">${__("Contacted")}</option>
                        <option value="Interested">${__("Interested")}</option>
                        <option value="Closed">${__("Closed")}</option>
                        <option value="Lost">${__("Lost")}</option>
                    </select>
                </div>
                <button class="btn btn-default btn-sm vc-btn-clear">${__("Clear Filters")}</button>
            </div>
            <div class="vc-tree-container"></div>
        `;
        this.$root.html(toolbarHtml);

        this.$container = this.$root.find(".vc-tree-container");

        // Event listeners
        let timer = null;
        this.$root.find(".vc-input-search").on("input", (e) => {
            clearTimeout(timer);
            timer = setTimeout(() => {
                this.filters.search = $(e.target).val().trim();
                this.load_categories();
            }, 300);
        });

        this.$root.find(".vc-select-status").on("change", (e) => {
            this.filters.status = $(e.target).val();
            this.load_categories();
        });

        this.$root.find(".vc-btn-clear").on("click", () => {
            this.filters = { search: "", status: "" };
            this.$root.find(".vc-input-search").val("");
            this.$root.find(".vc-select-status").val("");
            this.load_categories();
        });
    }

    get_api_filters() {
        const f = {};
        if (this.filters.search) f.search = this.filters.search;
        if (this.filters.status) f.status = [this.filters.status];
        return JSON.stringify(f);
    }

    async load_categories() {
        this.loading.categories = true;
        this.errors.categories = null;
        this.render();

        try {
            const res = await frappe.call({
                method: "visa_crm.api.lead_tree.get_lead_tree_nodes",
                args: {
                    parent_level: "Categories",
                    filters: this.get_api_filters()
                }
            });
            this.categories = res.message || [];
        } catch (e) {
            this.errors.categories = e.message || __("Failed to load categories");
        } finally {
            this.loading.categories = false;
            this.render();
        }
    }

    async load_subcategories(categoryName) {
        this.loading.subcategories[categoryName] = true;
        this.errors.subcategories[categoryName] = null;
        this.render();

        try {
            const res = await frappe.call({
                method: "visa_crm.api.lead_tree.get_lead_tree_nodes",
                args: {
                    parent_level: "Subcategories",
                    category: categoryName,
                    filters: this.get_api_filters()
                }
            });
            this.subcategories[categoryName] = res.message || [];
        } catch (e) {
            this.errors.subcategories[categoryName] = e.message || __("Failed to load subcategories");
        } finally {
            this.loading.subcategories[categoryName] = false;
            this.render();
        }
    }

    async load_leads(categoryName, subcategoryName, page = 1) {
        const key = `${categoryName}::${subcategoryName}`;
        this.loading.leads[key] = true;
        this.errors.leads[key] = null;
        this.render();

        try {
            const currentFilters = JSON.parse(this.get_api_filters());
            currentFilters.page = page;
            currentFilters.page_length = 20;

            const res = await frappe.call({
                method: "visa_crm.api.lead_tree.get_lead_tree_nodes",
                args: {
                    parent_level: "Leads",
                    category: categoryName,
                    subcategory: subcategoryName,
                    filters: JSON.stringify(currentFilters)
                }
            });
            const result = res.message || { data: [], has_more: false, page: 1 };

            if (page === 1) {
                this.leads[key] = result;
            } else {
                const existing = this.leads[key] ? this.leads[key].data : [];
                this.leads[key] = {
                    data: existing.concat(result.data || []),
                    has_more: result.has_more,
                    page: page
                };
            }
        } catch (e) {
            this.errors.leads[key] = e.message || __("Failed to load leads");
        } finally {
            this.loading.leads[key] = false;
            this.render();
        }
    }

    toggle_category(categoryName) {
        if (this.expandedCategories.has(categoryName)) {
            this.expandedCategories.delete(categoryName);
        } else {
            this.expandedCategories.add(categoryName);
            if (!this.subcategories[categoryName]) {
                this.load_subcategories(categoryName);
            }
        }
        this.render();
    }

    toggle_subcategory(categoryName, subcategoryName) {
        const key = `${categoryName}::${subcategoryName}`;
        if (this.expandedSubcategories.has(key)) {
            this.expandedSubcategories.delete(key);
        } else {
            this.expandedSubcategories.add(key);
            if (!this.leads[key]) {
                this.load_leads(categoryName, subcategoryName, 1);
            }
        }
        this.render();
    }

    render() {
        if (this.loading.categories) {
            this.$container.html(`
                <div class="vc-empty-state">
                    <div class="vc-spinner"></div>
                    <div>${__("Loading Lead Management...")}</div>
                </div>
            `);
            return;
        }

        if (this.errors.categories) {
            this.$container.html(`
                <div class="vc-error-state">
                    <div style="font-weight: 600; margin-bottom: 8px;">${__("Lead Management could not be loaded.")}</div>
                    <div class="vc-error-text">${frappe.utils.escape_html(this.errors.categories)}</div>
                    <button class="btn btn-default btn-xs vc-btn-retry-categories" style="margin-top: 12px;">${__("Retry")}</button>
                </div>
            `);
            this.$container.find(".vc-btn-retry-categories").on("click", () => this.load_categories());
            return;
        }

        if (!this.categories || this.categories.length === 0) {
            this.$container.html(`
                <div class="vc-empty-state">
                    <i class="octicon octicon-inbox" style="font-size:32px; opacity:0.5; margin-bottom:8px;"></i>
                    <div>${__("No lead categories found.")}</div>
                </div>
            `);
            return;
        }

        let html = '<div class="vc-tree-list">';
        for (const cat of this.categories) {
            const isCatExpanded = this.expandedCategories.has(cat.value);
            const catIcon = isCatExpanded ? "octicon-chevron-down" : "octicon-chevron-right";

            html += `
                <div class="vc-tree-node vc-level-category" data-category="${frappe.utils.escape_html(cat.value)}">
                    <div class="vc-node-header vc-cat-header">
                        <i class="vc-chevron octicon ${catIcon}"></i>
                        <i class="vc-folder-icon octicon octicon-file-directory"></i>
                        <span class="vc-node-title">${frappe.utils.escape_html(cat.label)}</span>
                        <span class="badge vc-badge-count">${cat.count || 0}</span>
                    </div>
            `;

            if (isCatExpanded) {
                html += '<div class="vc-node-children vc-cat-children">';
                if (this.loading.subcategories[cat.value]) {
                    html += `
                        <div class="vc-loading-inline">
                            <span class="vc-spinner-sm"></span> ${__("Loading subcategories...")}
                        </div>
                    `;
                } else if (this.errors.subcategories[cat.value]) {
                    html += `
                        <div class="vc-error-inline">
                            ${frappe.utils.escape_html(this.errors.subcategories[cat.value])}
                            <button class="btn btn-xs btn-default vc-btn-retry-sub" data-category="${frappe.utils.escape_html(cat.value)}">${__("Retry")}</button>
                        </div>
                    `;
                } else {
                    const subs = this.subcategories[cat.value] || [];
                    if (subs.length === 0) {
                        html += `<div class="vc-empty-inline">${__("No subcategories")}</div>`;
                    } else {
                        for (const sub of subs) {
                            const subKey = `${cat.value}::${sub.value}`;
                            const isSubExpanded = this.expandedSubcategories.has(subKey);
                            const subIcon = isSubExpanded ? "octicon-chevron-down" : "octicon-chevron-right";

                            html += `
                                <div class="vc-tree-node vc-level-subcategory" data-category="${frappe.utils.escape_html(cat.value)}" data-subcategory="${frappe.utils.escape_html(sub.value)}">
                                    <div class="vc-node-header vc-sub-header">
                                        <i class="vc-chevron octicon ${subIcon}"></i>
                                        <i class="vc-layer-icon octicon octicon-versions"></i>
                                        <span class="vc-node-title">${frappe.utils.escape_html(sub.label)}</span>
                                        <span class="badge vc-badge-count">${sub.count || 0}</span>
                                    </div>
                            `;

                            if (isSubExpanded) {
                                html += '<div class="vc-node-children vc-sub-children">';
                                if (this.loading.leads[subKey] && (!this.leads[subKey] || this.leads[subKey].page === 1)) {
                                    html += `
                                        <div class="vc-loading-inline">
                                            <span class="vc-spinner-sm"></span> ${__("Loading leads...")}
                                        </div>
                                    `;
                                } else if (this.errors.leads[subKey]) {
                                    html += `
                                        <div class="vc-error-inline">
                                            ${frappe.utils.escape_html(this.errors.leads[subKey])}
                                            <button class="btn btn-xs btn-default vc-btn-retry-leads" data-category="${frappe.utils.escape_html(cat.value)}" data-subcategory="${frappe.utils.escape_html(sub.value)}">${__("Retry")}</button>
                                        </div>
                                    `;
                                } else {
                                    const leadData = this.leads[subKey] || { data: [], has_more: false };
                                    const leadRows = leadData.data || [];
                                    if (leadRows.length === 0) {
                                        html += `<div class="vc-empty-inline">${__("No leads in this subcategory")}</div>`;
                                    } else {
                                        html += '<div class="vc-lead-table">';
                                        for (const lead of leadRows) {
                                            html += this.render_lead_row(lead);
                                        }
                                        html += '</div>';

                                        if (leadData.has_more) {
                                            html += `
                                                <div class="vc-load-more-wrap">
                                                    <button class="btn btn-xs btn-default vc-btn-load-more" data-category="${frappe.utils.escape_html(cat.value)}" data-subcategory="${frappe.utils.escape_html(sub.value)}" data-page="${leadData.page}">
                                                        ${this.loading.leads[subKey] ? __("Loading...") : __("Load More Leads")}
                                                    </button>
                                                </div>
                                            `;
                                        }
                                    }
                                }
                                html += '</div>'; // close vc-sub-children
                            }
                            html += '</div>'; // close vc-level-subcategory
                        }
                    }
                }
                html += '</div>'; // close vc-cat-children
            }
            html += '</div>'; // close vc-level-category
        }
        html += '</div>'; // close vc-tree-list

        this.$container.html(html);
        this.bind_tree_events();
    }

    render_lead_row(lead) {
        const name = frappe.utils.escape_html(lead.lead_name || lead.name);
        const leadId = frappe.utils.escape_html(lead.name);
        const status = frappe.utils.escape_html(lead.status || "Open");
        const owner = frappe.utils.escape_html(lead.lead_owner || __("Unassigned"));
        const modified = lead.modified ? frappe.datetime.global_date_format(lead.modified) : "";
        const phone = frappe.utils.escape_html(lead.mobile_no || lead.phone || "");
        const email = frappe.utils.escape_html(lead.email || "");

        let statusClass = "label-default";
        if (status === "Lead Qualified") statusClass = "label-success";
        else if (status === "New" || status === "Open") statusClass = "label-info";
        else if (status === "Contacted" || status === "Interested") statusClass = "label-warning";

        return `
            <div class="vc-lead-row" data-lead-id="${leadId}">
                <div class="vc-lead-cell vc-cell-main">
                    <span class="vc-lead-name">${name}</span>
                    <span class="vc-lead-id">${leadId}</span>
                </div>
                <div class="vc-lead-cell vc-cell-contact">
                    ${phone ? `<span><i class="octicon octicon-device-mobile"></i> ${phone}</span>` : ''}
                    ${email ? `<span class="text-muted"><i class="octicon octicon-mail"></i> ${email}</span>` : ''}
                </div>
                <div class="vc-lead-cell vc-cell-status">
                    <span class="label ${statusClass}">${status}</span>
                </div>
                <div class="vc-lead-cell vc-cell-owner">
                    <span class="text-muted"><i class="octicon octicon-person"></i> ${owner}</span>
                </div>
                <div class="vc-lead-cell vc-cell-date text-muted">
                    ${modified}
                </div>
            </div>
        `;
    }

    bind_tree_events() {
        // Toggle Category
        this.$container.find(".vc-cat-header").off("click").on("click", (e) => {
            e.stopPropagation();
            const cat = $(e.currentTarget).closest(".vc-level-category").data("category");
            if (cat) this.toggle_category(cat);
        });

        // Toggle Subcategory
        this.$container.find(".vc-sub-header").off("click").on("click", (e) => {
            e.stopPropagation();
            const cat = $(e.currentTarget).closest(".vc-level-subcategory").data("category");
            const sub = $(e.currentTarget).closest(".vc-level-subcategory").data("subcategory");
            if (cat && sub) this.toggle_subcategory(cat, sub);
        });

        // Click Lead Row
        this.$container.find(".vc-lead-row").off("click").on("click", (e) => {
            const leadId = $(e.currentTarget).data("lead-id");
            if (leadId) {
                frappe.set_route("Form", "CRM Lead", leadId);
            }
        });

        // Retry Category Subcategories
        this.$container.find(".vc-btn-retry-sub").off("click").on("click", (e) => {
            e.stopPropagation();
            const cat = $(e.currentTarget).data("category");
            if (cat) this.load_subcategories(cat);
        });

        // Retry Subcategory Leads
        this.$container.find(".vc-btn-retry-leads").off("click").on("click", (e) => {
            e.stopPropagation();
            const cat = $(e.currentTarget).data("category");
            const sub = $(e.currentTarget).data("subcategory");
            if (cat && sub) this.load_leads(cat, sub, 1);
        });

        // Load More Leads
        this.$container.find(".vc-btn-load-more").off("click").on("click", (e) => {
            e.stopPropagation();
            const cat = $(e.currentTarget).data("category");
            const sub = $(e.currentTarget).data("subcategory");
            const page = parseInt($(e.currentTarget).data("page") || 1) + 1;
            if (cat && sub) this.load_leads(cat, sub, page);
        });
    }

    inject_styles() {
        if ($("#vc-lead-tree-styles").length) return;
        $("<style id='vc-lead-tree-styles'>").text(`
            .vc-lead-tree-page { padding: 15px; max-width: 1200px; margin: 0 auto; }
            .vc-tree-toolbar { display: flex; gap: 10px; margin-bottom: 15px; align-items: center; flex-wrap: wrap; }
            .vc-search-box { flex: 1; min-width: 200px; }
            .vc-filter-box { width: 160px; }
            .vc-tree-container { background: var(--card-bg, #fff); border: 1px solid var(--border-color, #d1d8dd); border-radius: 6px; overflow: hidden; min-height: 200px; }

            .vc-tree-list { display: flex; flex-direction: column; }
            .vc-tree-node { border-bottom: 1px solid var(--border-color, #eef2f5); }
            .vc-tree-node:last-child { border-bottom: none; }

            .vc-node-header { display: flex; align-items: center; padding: 10px 14px; cursor: pointer; user-select: none; transition: background 0.15s ease; }
            .vc-node-header:hover { background: var(--hover-bg, #f7fafc); }
            .vc-cat-header { font-weight: 600; font-size: 14px; background: var(--control-bg, #f4f5f7); }
            .vc-sub-header { font-weight: 500; font-size: 13px; padding-left: 32px; background: var(--card-bg, #fff); }

            .vc-chevron { width: 16px; text-align: center; margin-right: 8px; color: var(--text-muted, #8d99a6); }
            .vc-folder-icon { margin-right: 8px; color: #3182ce; }
            .vc-layer-icon { margin-right: 8px; color: #805ad5; }
            .vc-node-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
            .vc-badge-count { background: var(--badge-bg, #edf2f7); color: var(--text-color, #2d3748); font-weight: 600; padding: 4px 8px; border-radius: 12px; margin-left: 8px; }

            .vc-cat-children { border-top: 1px solid var(--border-color, #eef2f5); }
            .vc-sub-children { border-top: 1px dashed var(--border-color, #eef2f5); padding-left: 20px; background: var(--sub-bg, #fafbfc); }

            .vc-lead-table { display: flex; flex-direction: column; }
            .vc-lead-row { display: flex; align-items: center; padding: 8px 14px; border-bottom: 1px solid var(--border-color, #edf2f7); cursor: pointer; transition: background 0.15s ease; font-size: 12px; }
            .vc-lead-row:last-child { border-bottom: none; }
            .vc-lead-row:hover { background: var(--hover-bg, #edf2f7); }

            .vc-lead-cell { padding: 0 6px; }
            .vc-cell-main { flex: 2; min-width: 150px; display: flex; flex-direction: column; }
            .vc-lead-name { font-weight: 600; color: var(--text-color, #1a202c); }
            .vc-lead-id { font-size: 10px; color: var(--text-muted, #718096); }
            .vc-cell-contact { flex: 2; min-width: 150px; display: flex; flex-direction: column; }
            .vc-cell-status { width: 110px; text-align: center; }
            .vc-cell-owner { width: 130px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
            .vc-cell-date { width: 90px; text-align: right; font-size: 11px; }

            .vc-loading-inline, .vc-error-inline, .vc-empty-inline { padding: 10px 14px 10px 48px; font-size: 12px; color: var(--text-muted, #718096); }
            .vc-error-inline { color: var(--danger-text, #e53e3e); }
            .vc-empty-state, .vc-error-state { padding: 40px 20px; text-align: center; color: var(--text-muted, #718096); }
            .vc-error-state { color: var(--danger-text, #e53e3e); }

            .vc-spinner { display: inline-block; width: 24px; height: 24px; border: 3px solid rgba(0,0,0,0.1); border-top-color: #3182ce; border-radius: 50%; animation: vc-spin 0.8s linear infinite; margin-bottom: 8px; }
            .vc-spinner-sm { display: inline-block; width: 12px; height: 12px; border: 2px solid rgba(0,0,0,0.1); border-top-color: #3182ce; border-radius: 50%; animation: vc-spin 0.8s linear infinite; vertical-align: middle; margin-right: 4px; }
            @keyframes vc-spin { to { transform: rotate(360deg); } }

            .vc-load-more-wrap { padding: 8px 14px 8px 48px; }
        `).appendTo(document.head);
    }
}
