/**
 * Lead Management — 3-Level Hierarchical Navigation
 *
 * URL state is encoded in the hash:
 *   (blank)                                       → Page 1: Categories
 *   #category/<encodedCategory>                   → Page 2: Subcategories
 *   #category/<enc>/subcategory/<enc>             → Page 3: Leads
 *
 * Browser back/forward works via hashchange.
 * Hard refresh restores the correct page by reading the hash.
 * Direct URL navigation with a hash opens the correct page.
 */

/* ─── Page lifecycle ─────────────────────────────────────────────── */

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

/* ─── Main controller ────────────────────────────────────────────── */

window.VisaLeadManagement = class VisaLeadManagement {
    constructor(page, wrapper) {
        this.page = page;
        this.wrapper = wrapper;
        this._inject_styles();
        this.$root = $('<div class="vlm-root"></div>').appendTo(page.body);

        // Cache: avoid re-fetching when navigating back
        this._cat_cache = null;
        this._sub_cache = {};   // key: category
        this._lead_cache = {};  // key: "cat::sub"

        // Bind hashchange so browser back/forward works
        this._onhash = () => this.handle_route();
        window.addEventListener("hashchange", this._onhash);

        this.handle_route();
    }

    /* ─── Router ─────────────────────────────────────────────────── */

    handle_route() {
        const { level, category, subcategory } = _parse_hash(window.location.hash);
        if (level === "leads") {
            this._show_leads(category, subcategory);
        } else if (level === "subcategories") {
            this._show_subcategories(category);
        } else {
            this._show_categories();
        }
    }

    /* ─── Page 1: Categories ──────────────────────────────────────── */

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
            this.$root.html(_tpl_empty(__("No lead categories found."),
                __("Leads arriving from Meta will appear here once they are categorized.")));
            return;
        }

        let html = `
            <div class="vlm-page">
                <div class="vlm-page-header">
                    <h2 class="vlm-page-title">${__("Categories")}</h2>
                    <p class="vlm-page-subtitle">${__("Select a category to view subcategories and leads.")}</p>
                </div>
                <div class="vlm-grid">`;

        for (const cat of cats) {
            const encodedCat = encodeURIComponent(cat.value);
            html += `
                <div class="vlm-card" data-href="#category/${encodedCat}" tabindex="0" role="button"
                     aria-label="${frappe.utils.escape_html(cat.label)}: ${cat.count} leads">
                    <div class="vlm-card-icon">
                        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/>
                        </svg>
                    </div>
                    <div class="vlm-card-body">
                        <div class="vlm-card-title">${frappe.utils.escape_html(cat.label)}</div>
                        <div class="vlm-card-count">${cat.count} ${__(cat.count === 1 ? "lead" : "leads")}</div>
                    </div>
                    <div class="vlm-card-arrow">›</div>
                </div>`;
        }

        html += `</div></div>`;
        this.$root.html(html);
        this.$root.find(".vlm-card").on("click keydown", function (e) {
            if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
            const href = $(this).data("href");
            if (href) window.location.hash = href;
        });
    }

    /* ─── Page 2: Subcategories ───────────────────────────────────── */

    async _show_subcategories(category) {
        const title = frappe.utils.escape_html(category);
        this.page.set_title(__("Lead Management") + " — " + title);
        this.page.clear_primary_action();
        this.page.clear_secondary_action();
        this.page.set_secondary_action(__("← Back"), () => {
            window.location.hash = "";
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
        const encodedCat = encodeURIComponent(category);
        const escapedCat = frappe.utils.escape_html(category);

        let html = `
            <div class="vlm-page">
                <div class="vlm-breadcrumb">
                    <a href="#" class="vlm-breadcrumb-link vlm-back">${__("Lead Management")}</a>
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
                const encodedSub = encodeURIComponent(sub.value);
                const hash = `#category/${encodedCat}/subcategory/${encodedSub}`;
                html += `
                    <div class="vlm-card vlm-card-sub" data-href="${hash}" tabindex="0" role="button"
                         aria-label="${frappe.utils.escape_html(sub.label)}: ${sub.count} leads">
                        <div class="vlm-card-icon vlm-icon-sub">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M4 6h16M4 10h16M4 14h8M4 18h8"/>
                            </svg>
                        </div>
                        <div class="vlm-card-body">
                            <div class="vlm-card-title">${frappe.utils.escape_html(sub.label)}</div>
                            <div class="vlm-card-count">${sub.count} ${__(sub.count === 1 ? "lead" : "leads")}</div>
                        </div>
                        <div class="vlm-card-arrow">›</div>
                    </div>`;
            }
            html += '</div>';
        }

        html += `</div>`;
        this.$root.html(html);

        this.$root.find(".vlm-back").on("click", (e) => {
            e.preventDefault();
            window.location.hash = "";
        });
        this.$root.find(".vlm-card").on("click keydown", function (e) {
            if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
            const href = $(this).data("href");
            if (href) window.location.hash = href;
        });
    }

    /* ─── Page 3: Leads ───────────────────────────────────────────── */

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
        const encodedCat = encodeURIComponent(category);
        const escapedCat = frappe.utils.escape_html(category);
        const escapedSub = frappe.utils.escape_html(subcategory);

        this.page.set_title(escapedCat + " / " + escapedSub);
        this.page.clear_primary_action();
        this.page.clear_secondary_action();
        this.page.set_secondary_action(__("← Back"), () => {
            window.location.hash = `#category/${encodedCat}`;
        }, "left");

        const state = this._get_lead_state(category, subcategory);
        this._render_lead_page(category, subcategory, state);

        if (!state.loaded && !state.loading) {
            this._fetch_leads(category, subcategory, 1);
        }
    }

    _render_lead_page(category, subcategory, state) {
        const encodedCat = encodeURIComponent(category);
        const escapedCat = frappe.utils.escape_html(category);
        const escapedSub = frappe.utils.escape_html(subcategory);

        const html = `
            <div class="vlm-page vlm-leads-page">
                <div class="vlm-breadcrumb">
                    <a href="#" class="vlm-breadcrumb-link vlm-back-root">${__("Lead Management")}</a>
                    <span class="vlm-breadcrumb-sep">›</span>
                    <a href="#category/${encodedCat}" class="vlm-breadcrumb-link vlm-back-cat">${escapedCat}</a>
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
                        <button class="btn btn-default btn-sm vlm-btn-clear">${__("Clear")}</button>
                    </div>
                </div>
                <div class="vlm-lead-content" id="vlm-lead-content"></div>
            </div>`;

        this.$root.html(html);

        // Bind breadcrumb links
        this.$root.find(".vlm-back-root").on("click", (e) => {
            e.preventDefault();
            window.location.hash = "";
        });
        this.$root.find(".vlm-back-cat").on("click", (e) => {
            e.preventDefault();
            window.location.hash = `#category/${encodedCat}`;
        });

        // Search with debounce
        let _searchTimer = null;
        this.$root.find(".vlm-search").on("input", (e) => {
            clearTimeout(_searchTimer);
            _searchTimer = setTimeout(() => {
                const s = this._get_lead_state(category, subcategory);
                s.search = $(e.target).val().trim();
                s.data = [];
                s.page = 1;
                s.loaded = false;
                this._fetch_leads(category, subcategory, 1);
            }, 300);
        });

        // Status filter
        this.$root.find(".vlm-status-filter").on("change", (e) => {
            const s = this._get_lead_state(category, subcategory);
            s.status = $(e.target).val();
            s.data = [];
            s.page = 1;
            s.loaded = false;
            this._fetch_leads(category, subcategory, 1);
        });

        // Clear filters
        this.$root.find(".vlm-btn-clear").on("click", () => {
            const s = this._get_lead_state(category, subcategory);
            s.search = "";
            s.status = "";
            s.data = [];
            s.page = 1;
            s.loaded = false;
            this.$root.find(".vlm-search").val("");
            this.$root.find(".vlm-status-filter").val("");
            this._fetch_leads(category, subcategory, 1);
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
                state.search || state.status
                    ? __("No leads match the current filters.")
                    : __("This subcategory has no leads yet.")
            ));
            return;
        }

        let html = `
            <div class="vlm-lead-table-wrap">
                <div class="vlm-lead-table-header">
                    <div class="vlm-th vlm-th-name">${__("Lead")}</div>
                    <div class="vlm-th vlm-th-status">${__("Status")}</div>
                    <div class="vlm-th vlm-th-contact">${__("Contact")}</div>
                    <div class="vlm-th vlm-th-owner">${__("Owner")}</div>
                    <div class="vlm-th vlm-th-date">${__("Modified")}</div>
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
                <div class="vlm-lead-row" data-lead="${id}" tabindex="0" role="button"
                     title="${__("Open in CRM")}">
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

        // Click lead row → open native CRM Lead detail
        $content.find(".vlm-lead-row").on("click keydown", function (e) {
            if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
            const leadId = $(this).data("lead");
            if (leadId) {
                window.location.href = "/crm/leads/" + encodeURIComponent(leadId) + "#activity";
            }
        });

        // Load more
        $content.find(".vlm-btn-load-more").on("click", () => {
            if (!state.loading && state.has_more) {
                this._fetch_leads(category, subcategory, state.page + 1);
            }
        });
    }

    /* ─── Error / loading states ─────────────────────────────────── */

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

    /* ─── Styles ─────────────────────────────────────────────────── */

    _inject_styles() {
        if (document.getElementById("vlm-styles")) return;
        const s = document.createElement("style");
        s.id = "vlm-styles";
        s.textContent = `
/* ─ Root ─ */
.vlm-root { padding: 20px; max-width: 1100px; margin: 0 auto; font-family: var(--font-stack, system-ui, sans-serif); }
.vlm-page { }

/* ─ Breadcrumb ─ */
.vlm-breadcrumb { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-muted, #8d99a6); margin-bottom: 12px; }
.vlm-breadcrumb-link { color: var(--text-muted, #8d99a6); text-decoration: none; cursor: pointer; }
.vlm-breadcrumb-link:hover { color: var(--text-color, #2d3748); text-decoration: underline; }
.vlm-breadcrumb-sep { opacity: 0.5; }
.vlm-breadcrumb-current { color: var(--text-color, #1a202c); font-weight: 500; }

/* ─ Page header ─ */
.vlm-page-header { margin-bottom: 20px; }
.vlm-page-title { font-size: 22px; font-weight: 700; margin: 0 0 4px; color: var(--heading-color, #1a202c); }
.vlm-page-subtitle { font-size: 13px; color: var(--text-muted, #8d99a6); margin: 0; }

/* ─ Card grid ─ */
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

/* ─ Lead list page ─ */
.vlm-lead-header { display: flex; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
.vlm-lead-toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.vlm-search { width: 220px; }
.vlm-status-filter { width: 150px; }
.vlm-lead-subtitle { font-size: 12px; color: var(--text-muted, #718096); }

/* ─ Lead table ─ */
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

/* ─ Status badges ─ */
.vlm-status-badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; white-space: nowrap; }
.vlm-badge-qualified { background: #c6f6d5; color: #276749; }
.vlm-badge-new, .vlm-badge-open { background: #bee3f8; color: #2a69ac; }
.vlm-badge-contacted, .vlm-badge-interested { background: #fefcbf; color: #975a16; }
.vlm-badge-closed { background: #e9d8fd; color: #553c9a; }
.vlm-badge-lost { background: #fed7d7; color: #9b2c2c; }
.vlm-badge-default { background: #edf2f7; color: #4a5568; }

/* ─ Load more ─ */
.vlm-load-more-wrap { padding: 14px; text-align: center; }

/* ─ State panels ─ */
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

/* ─── Hash routing helpers ───────────────────────────────────────── */

function _parse_hash(hash) {
    const h = (hash || "").replace(/^#/, "");
    if (!h || h === "categories") {
        return { level: "categories", category: null, subcategory: null };
    }
    // #category/<cat>/subcategory/<sub>
    const leadMatch = h.match(/^category\/([^\/]+)\/subcategory\/(.+)$/);
    if (leadMatch) {
        return {
            level: "leads",
            category: decodeURIComponent(leadMatch[1]),
            subcategory: decodeURIComponent(leadMatch[2])
        };
    }
    // #category/<cat>
    const subMatch = h.match(/^category\/([^\/]+)$/);
    if (subMatch) {
        return {
            level: "subcategories",
            category: decodeURIComponent(subMatch[1]),
            subcategory: null
        };
    }
    return { level: "categories", category: null, subcategory: null };
}

/* ─── Render helper templates ────────────────────────────────────── */

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
