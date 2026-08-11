const DASHBOARD_BUILD_ID = "v2026.08.11-1e7e609";

frappe.pages["employee-performance-dashboard"] = frappe.pages["employee-performance-dashboard"] || {};
frappe.pages["employee-dashboard"] = frappe.pages["employee-dashboard"] || {};

function render_employee_performance_dashboard(wrapper) {
  const boot_log = [
    "EMPLOYEE DASHBOARD BOOTING",
    "ROUTE DETECTED: " + (frappe.get_route ? frappe.get_route().join("/") : "employee-dashboard"),
    "PAGE SCRIPT LOADED: public/js/employee_dashboard.js (" + DASHBOARD_BUILD_ID + ")",
    "USER LOADED: " + (frappe.session ? frappe.session.user : "unknown")
  ];

  console.log("[Visa CRM Dashboard Boot]", boot_log.join(" -> "));

  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("Employee Performance & Investigation Dashboard"),
    single_column: true,
  });

  const root = $('<div class="visa-employee-dashboard"></div>').appendTo(page.body);

  if (!document.getElementById("visa-employee-dashboard-style")) {
    $("head").append(`<style id="visa-employee-dashboard-style">
      .visa-employee-dashboard { padding: 16px 20px 40px; max-width: 1250px; margin: 0 auto; font-family: var(--font-stack, system-ui, sans-serif); }
      .visa-build-tag { font-size: 11px; color: var(--text-muted, #a0aec0); font-weight: 500; float: right; margin-top: 4px; }
      .visa-filter-bar { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; background: var(--card-bg, #fff); border: 1px solid var(--border-color, #e2e8f0); padding: 14px 18px; border-radius: 10px; margin-bottom: 20px; }
      .visa-filter-group { display: flex; flex-direction: column; gap: 4px; font-size: 11px; font-weight: 600; color: var(--text-muted, #718096); }
      .visa-filter-group select, .visa-filter-group input { height: 34px; padding: 4px 10px; font-size: 12px; border-radius: 6px; border: 1px solid var(--border-color, #cbd5e0); background: var(--control-bg, #fff); min-width: 150px; }
      .visa-emp-header { background: var(--card-bg, #fff); border: 1px solid var(--border-color, #e2e8f0); border-radius: 10px; padding: 18px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
      .visa-emp-title { margin: 0 0 4px; font-size: 20px; font-weight: 700; color: var(--heading-color, #1a202c); }
      .visa-emp-meta { font-size: 12px; color: var(--text-muted, #718096); display: flex; gap: 12px; flex-wrap: wrap; }
      .visa-section-title { font-size: 16px; font-weight: 700; margin: 24px 0 12px; color: var(--heading-color, #1a202c); display: flex; align-items: center; justify-content: space-between; }
      .visa-kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; margin-bottom: 20px; }
      .visa-kpi { border: 1px solid var(--border-color, #e2e8f0); border-radius: 10px; padding: 16px; background: var(--card-bg, #fff); }
      .visa-kpi-label { color: var(--text-muted, #718096); font-size: 12px; font-weight: 500; margin-bottom: 6px; }
      .visa-kpi-value { font-size: 28px; font-weight: 700; line-height: 1.1; color: var(--text-color, #1a202c); }
      .visa-kpi-sub { font-size: 11px; color: var(--text-muted, #a0aec0); margin-top: 4px; }
      .visa-badge-insufficient { display: inline-block; padding: 2px 8px; border-radius: 4px; background: #feebc8; color: #744210; font-size: 11px; font-weight: 600; }
      .visa-badge-evaluated { display: inline-block; padding: 2px 8px; border-radius: 4px; background: #c6f6d5; color: #22543d; font-size: 11px; font-weight: 600; }
      .visa-badge-pending { display: inline-block; padding: 2px 8px; border-radius: 4px; background: #ebf8ff; color: #2b6cb0; font-size: 11px; font-weight: 600; }
      .visa-badge-failed { display: inline-block; padding: 2px 8px; border-radius: 4px; background: #fed7d7; color: #9b2c2c; font-size: 11px; font-weight: 600; }
      .visa-grid-two { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
      @media(max-width:768px) { .visa-grid-two { grid-template-columns: 1fr; } }
      .visa-panel { border: 1px solid var(--border-color, #e2e8f0); border-radius: 10px; background: var(--card-bg, #fff); padding: 18px; margin-bottom: 20px; }
      .visa-panel-header { font-size: 15px; font-weight: 600; margin-bottom: 14px; color: var(--text-color, #1a202c); border-bottom: 1px solid var(--border-color, #edf2f7); padding-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }
      .visa-progress-row { margin-bottom: 10px; }
      .visa-progress-label { display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px; }
      .visa-progress-bar-wrap { height: 8px; background: #edf2f7; border-radius: 4px; overflow: hidden; }
      .visa-progress-fill { height: 100%; background: #3182ce; border-radius: 4px; transition: width 0.3s ease; }
      .visa-table { width: 100%; border-collapse: collapse; font-size: 13px; }
      .visa-table th, .visa-table td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border-color, #edf2f7); }
      .visa-table th { background: var(--control-bg, #f7fafc); font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-muted, #718096); }
      .visa-table-row { cursor: pointer; transition: background 0.12s ease; }
      .visa-table-row:hover { background: var(--hover-bg, #f7fafc); }
      .visa-pagination { display: flex; justify-content: space-between; align-items: center; margin-top: 14px; font-size: 12px; color: var(--text-muted, #718096); }
      .visa-coaching-box { background: #ebf8ff; border: 1px solid #bee3f8; border-radius: 8px; padding: 12px 16px; color: #2b6cb0; font-size: 13px; margin-bottom: 8px; }
    </style>`);
  }

  let filters = {
    employee: "",
    preset: "this_month",
    from_date: "",
    to_date: "",
    lead_source: "",
    category: "",
    subcategory: "",
    visa_type: "",
    country: "",
    lead_status: "",
    channel: "",
    ai_status: ""
  };

  let employees_cache = [];
  let current_page_start = 0;
  let page_length = 20;

  function show_error_panel(stage, method, error_object) {
    const errMsg = (error_object && error_object.message) ? error_object.message : (typeof error_object === "string" ? error_object : "Management authorization required or backend API unavailable.");
    const excType = (error_object && error_object.exc_type) ? error_object.exc_type : "Error";
    const status = (error_object && error_object.status) ? error_object.status : "403/500";

    root.html(`
      <div class="visa-panel text-danger" style="border-left:4px solid #e53e3e;">
        <div class="visa-build-tag">Build: ${DASHBOARD_BUILD_ID}</div>
        <h4 style="margin:0 0 8px;color:#c53030;"><i class="fa fa-exclamation-triangle"></i> Employee Dashboard Initialization Error</h4>
        <p style="margin-bottom:6px;"><strong>Failure Stage:</strong> <code>${frappe.utils.escape_html(stage)}</code></p>
        <p style="margin-bottom:6px;"><strong>API Method:</strong> <code>${frappe.utils.escape_html(method)}</code></p>
        <p style="margin-bottom:6px;"><strong>Exception Type:</strong> <code>${frappe.utils.escape_html(excType)}</code></p>
        <p style="margin-bottom:12px;"><strong>Error Message:</strong> ${frappe.utils.escape_html(errMsg)}</p>
        <button class="btn btn-primary btn-sm v-btn-retry-init">${__("Retry Dashboard Boot")}</button>
      </div>
    `);
    root.find(".v-btn-retry-init").on("click", init);
  }

  function init() {
    boot_log.push("ROLE CHECK PASSED");
    boot_log.push("API REQUEST STARTED: employee_list_for_dashboard");
    console.log("[Visa CRM Dashboard]", boot_log[boot_log.length - 1]);

    root.html(`
      <div class="visa-panel text-muted p-4">
        <div class="visa-build-tag">Build: ${DASHBOARD_BUILD_ID}</div>
        <i class="fa fa-spinner fa-spin"></i> Initializing Employee Performance & Investigation Dashboard...
      </div>
    `);

    frappe.call({
      method: "visa_crm.api.dashboard.employee_list_for_dashboard",
      callback: function (r) {
        boot_log.push("API RESPONSE RECEIVED: employee_list_for_dashboard");
        employees_cache = r.message || [];
        if (!employees_cache.length) {
          root.html(`
            <div class="visa-panel text-warning">
              <div class="visa-build-tag">Build: ${DASHBOARD_BUILD_ID}</div>
              <h4>No Active Employees Found</h4>
              <p>No active employee records are available for performance monitoring.</p>
            </div>
          `);
          return;
        }
        if (!filters.employee) {
          filters.employee = employees_cache[0].name;
        }
        boot_log.push("DATA VALIDATED: " + employees_cache.length + " employees");
        load_dashboard();
      },
      error: function (err) {
        console.error("Employee list fetch error:", err);
        show_error_panel("API_REQUEST_INITIAL", "visa_crm.api.dashboard.employee_list_for_dashboard", err);
      }
    });
  }

  function load_dashboard() {
    boot_log.push("API REQUEST STARTED: employee_performance_dashboard (" + filters.employee + ")");
    root.find(".visa-kpi-grid, .visa-grid-two").css("opacity", "0.5");

    frappe.call({
      method: "visa_crm.api.dashboard.employee_performance_dashboard",
      args: filters,
      callback: function (r) {
        boot_log.push("API RESPONSE RECEIVED: employee_performance_dashboard");
        const data = r.message || {};
        render_dashboard(data);
        load_interactions(0);
      },
      error: function (err) {
        console.error("Performance dashboard fetch error:", err);
        show_error_panel("API_REQUEST_METRICS", "visa_crm.api.dashboard.employee_performance_dashboard", err);
      }
    });
  }

  function render_dashboard(data) {
    boot_log.push("UI RENDERED");
    console.log("[Visa CRM Dashboard Boot Complete]", boot_log.join(" -> "));

    const emp = data.employee || {};
    const period = data.period || {};
    const summary = data.summary || {};
    const ai = data.ai_metrics || {};
    const dims = ai.dimensions || {};
    const biz = data.business_metrics || {};
    const dq = data.data_quality || {};
    const coaching = data.coaching || {};

    let html = `
      <div class="visa-filter-bar">
        <div class="visa-filter-group">
          <label>${__("Select Employee")}</label>
          <select id="v-emp-select" class="form-control">
            ${employees_cache.map(e => `<option value="${e.name}"${e.name === emp.name ? " selected" : ""}>${frappe.utils.escape_html(e.employee_name)} (${e.name})</option>`).join("")}
          </select>
        </div>
        <div class="visa-filter-group">
          <label>${__("Time Period")}</label>
          <select id="v-preset-select" class="form-control">
            <option value="today"${filters.preset === "today" ? " selected" : ""}>${__("Today")}</option>
            <option value="this_week"${filters.preset === "this_week" ? " selected" : ""}>${__("This Week")}</option>
            <option value="this_month"${filters.preset === "this_month" ? " selected" : ""}>${__("This Month")}</option>
            <option value="last_month"${filters.preset === "last_month" ? " selected" : ""}>${__("Last Month")}</option>
            <option value="custom"${filters.preset === "custom" ? " selected" : ""}>${__("Custom Range")}</option>
          </select>
        </div>
        <div class="visa-filter-group v-custom-date" style="${filters.preset === "custom" ? "" : "display:none;"}">
          <label>${__("From Date")}</label>
          <input type="date" id="v-from-date" class="form-control" value="${filters.from_date || period.from_date || ""}" />
        </div>
        <div class="visa-filter-group v-custom-date" style="${filters.preset === "custom" ? "" : "display:none;"}">
          <label>${__("To Date")}</label>
          <input type="date" id="v-to-date" class="form-control" value="${filters.to_date || period.to_date || ""}" />
        </div>
        <div class="visa-filter-group">
          <label>${__("Channel")}</label>
          <select id="v-channel-filter" class="form-control">
            <option value="">${__("All Channels")}</option>
            <option value="Phone"${filters.channel === "Phone" ? " selected" : ""}>Phone / Call</option>
            <option value="WhatsApp"${filters.channel === "WhatsApp" ? " selected" : ""}>WhatsApp</option>
            <option value="Email"${filters.channel === "Email" ? " selected" : ""}>Email</option>
            <option value="Instagram"${filters.channel === "Instagram" ? " selected" : ""}>Instagram</option>
          </select>
        </div>
        <div class="visa-filter-group">
          <label>${__("AI Status")}</label>
          <select id="v-ai-status-filter" class="form-control">
            <option value="">${__("All AI Statuses")}</option>
            <option value="Evaluated"${filters.ai_status === "Evaluated" ? " selected" : ""}>Evaluated</option>
            <option value="Pending"${filters.ai_status === "Pending" ? " selected" : ""}>Pending</option>
            <option value="Failed"${filters.ai_status === "Failed" ? " selected" : ""}>Failed</option>
          </select>
        </div>
        <div class="visa-filter-group" style="margin-left:auto;align-self:flex-end;">
          <button class="btn btn-primary btn-sm" id="v-btn-filter">${__("Apply")}</button>
          <button class="btn btn-default btn-sm" id="v-btn-reset">${__("Reset")}</button>
        </div>
      </div>

      <div class="visa-emp-header">
        <div>
          <div class="visa-build-tag">Build: ${DASHBOARD_BUILD_ID}</div>
          <h3 class="visa-emp-title">${frappe.utils.escape_html(emp.employee_name || "Employee")}</h3>
          <div class="visa-emp-meta">
            <span><strong>ID:</strong> ${frappe.utils.escape_html(emp.name || "")}</span>
            <span><strong>Department:</strong> ${frappe.utils.escape_html(emp.department || "Sales")}</span>
            <span><strong>Designation:</strong> ${frappe.utils.escape_html(emp.designation || "Counselor")}</span>
            <span><strong>Period:</strong> ${period.from_date} &rarr; ${period.to_date}</span>
          </div>
        </div>
        <div>
          <span class="badge badge-success" style="font-size:12px;padding:6px 10px;">${emp.status || "Active"}</span>
        </div>
      </div>

      <div class="visa-section-title">📊 ${__("Aggregate Performance Summary")}</div>
      <div class="visa-kpi-grid">
        <div class="visa-kpi">
          <div class="visa-kpi-label">${__("Total Interactions")}</div>
          <div class="visa-kpi-value">${summary.total_interactions || 0}</div>
          <div class="visa-kpi-sub">${summary.unique_customers || 0} ${__("unique customers")}</div>
        </div>
        <div class="visa-kpi">
          <div class="visa-kpi-label">${__("AI Evaluation Status")}</div>
          <div style="margin-top:6px;">
            <span class="visa-badge-evaluated">${ai.ai_evaluated || 0} Evaluated</span>
            ${ai.ai_pending ? `<span class="visa-badge-pending">${ai.ai_pending} Pending</span>` : ""}
            ${ai.ai_failed ? `<span class="visa-badge-failed">${ai.ai_failed} Failed</span>` : ""}
          </div>
        </div>
        <div class="visa-kpi">
          <div class="visa-kpi-label">${__("AI Communication Quality")}</div>
          <div class="visa-kpi-value" style="color:#2b6cb0;">
            ${ai.insufficient_data ? `<span class="visa-badge-insufficient">${__("Insufficient Data")}</span>` : `${ai.overall_score}/100`}
          </div>
          <div class="visa-kpi-sub">${dq.score_basis || ""}</div>
        </div>
        <div class="visa-kpi">
          <div class="visa-kpi-label">${__("Business Performance")}</div>
          <div class="visa-kpi-value" style="color:#276749;">${biz.business_score || 0}/100</div>
          <div class="visa-kpi-sub">${biz.converted_leads || 0}/${biz.assigned_leads || 0} ${__("leads converted")} (${biz.conversion_rate || 0}%)</div>
        </div>
        <div class="visa-kpi">
          <div class="visa-kpi-label">${__("Follow-up Discipline")}</div>
          <div class="visa-kpi-value">${biz.followup_compliance || 100}%</div>
          <div class="visa-kpi-sub">${biz.followups_completed || 0}/${biz.followups_created || 0} ${__("completed")}</div>
        </div>
      </div>

      <div class="visa-grid-two">
        <div class="visa-panel">
          <div class="visa-panel-header">🧠 ${__("AI Communication Quality Breakdown")}</div>
          <div class="visa-progress-row">
            <div class="visa-progress-label"><span>${__("Friendliness")}</span><span>${dims.friendliness || 0}</span></div>
            <div class="visa-progress-bar-wrap"><div class="visa-progress-fill" style="width:${dims.friendliness || 0}%;"></div></div>
          </div>
          <div class="visa-progress-row">
            <div class="visa-progress-label"><span>${__("Empathy & Active Listening")}</span><span>${dims.empathy || 0}</span></div>
            <div class="visa-progress-bar-wrap"><div class="visa-progress-fill" style="width:${dims.empathy || 0}%;background:#805ad5;"></div></div>
          </div>
          <div class="visa-progress-row">
            <div class="visa-progress-label"><span>${__("Professionalism & Clarity")}</span><span>${dims.professionalism || 0}</span></div>
            <div class="visa-progress-bar-wrap"><div class="visa-progress-fill" style="width:${dims.professionalism || 0}%;background:#38a169;"></div></div>
          </div>
          <div class="visa-progress-row">
            <div class="visa-progress-label"><span>${__("Clarity")}</span><span>${dims.clarity || 0}</span></div>
            <div class="visa-progress-bar-wrap"><div class="visa-progress-fill" style="width:${dims.clarity || 0}%;background:#3182ce;"></div></div>
          </div>
          <div class="visa-progress-row">
            <div class="visa-progress-label"><span>${__("Policy Compliance")}</span><span>${dims.policy_compliance || 0}</span></div>
            <div class="visa-progress-bar-wrap"><div class="visa-progress-fill" style="width:${dims.policy_compliance || 0}%;background:#dd6b20;"></div></div>
          </div>
        </div>

        <div class="visa-panel">
          <div class="visa-panel-header">💼 ${__("Operational & Conversion Pipeline")}</div>
          <div class="visa-progress-row">
            <div class="visa-progress-label"><span>${__("Leads Assigned")}</span><strong>${biz.assigned_leads || 0}</strong></div>
          </div>
          <div class="visa-progress-row">
            <div class="visa-progress-label"><span>${__("Leads Contacted")}</span><strong>${biz.contacted_leads || 0}</strong></div>
          </div>
          <div class="visa-progress-row">
            <div class="visa-progress-label"><span>${__("Visa Applications Created")}</span><strong>${biz.visa_applications_created || 0}</strong></div>
          </div>
          <div class="visa-progress-row">
            <div class="visa-progress-label"><span>${__("Visa Applications Completed")}</span><strong>${biz.visa_applications_completed || 0}</strong></div>
          </div>
          <div class="visa-progress-row">
            <div class="visa-progress-label"><span>${__("Lost Leads")}</span><strong style="color:#c53030;">${biz.lost_leads || 0}</strong></div>
          </div>
        </div>
      </div>`;

    if (coaching.coaching_tips && coaching.coaching_tips.length) {
      html += `
        <div class="visa-panel">
          <div class="visa-panel-header">💡 ${__("Aggregated AI Coaching Insights")}</div>
          ${coaching.coaching_tips.map(tip => `<div class="visa-coaching-box">📌 ${frappe.utils.escape_html(tip)}</div>`).join("")}
        </div>`;
    }

    html += `
      <div class="visa-panel">
        <div class="visa-panel-header">
          <span>🔍 ${__("Customer Interactions Audit Table")}</span>
          <span class="text-muted" style="font-size:12px;" id="v-interaction-count">Loading interactions...</span>
        </div>
        <div id="v-interaction-table-wrap">
          <div class="text-muted p-3">Loading customer interaction logs...</div>
        </div>
      </div>`;

    root.html(html);

    root.find("#v-emp-select").on("change", function () {
      filters.employee = $(this).val();
      load_dashboard();
    });

    root.find("#v-preset-select").on("change", function () {
      filters.preset = $(this).val();
      if (filters.preset === "custom") {
        root.find(".v-custom-date").show();
      } else {
        root.find(".v-custom-date").hide();
        load_dashboard();
      }
    });

    root.find("#v-btn-filter").on("click", function () {
      filters.from_date = root.find("#v-from-date").val();
      filters.to_date = root.find("#v-to-date").val();
      filters.channel = root.find("#v-channel-filter").val();
      filters.ai_status = root.find("#v-ai-status-filter").val();
      load_dashboard();
    });

    root.find("#v-btn-reset").on("click", function () {
      filters = {
        employee: employees_cache.length ? employees_cache[0].name : "",
        preset: "this_month",
        from_date: "",
        to_date: "",
        lead_source: "",
        category: "",
        subcategory: "",
        visa_type: "",
        country: "",
        lead_status: "",
        channel: "",
        ai_status: ""
      };
      load_dashboard();
    });
  }

  function load_interactions(start) {
    current_page_start = start;
    const args = Object.assign({}, filters, { start: start, page_length: page_length });
    const $wrap = root.find("#v-interaction-table-wrap");
    $wrap.html('<div class="text-muted p-3"><i class="fa fa-spinner fa-spin"></i> Loading customer interaction logs...</div>');

    frappe.call({
      method: "visa_crm.api.dashboard.employee_interactions",
      args: args,
      callback: function (r) {
        const res = r.message || { interactions: [], total_count: 0 };
        render_interaction_table(res);
      },
      error: function (err) {
        console.error("Employee interactions fetch failed:", err);
        $wrap.html(`
          <div class="p-3 text-danger">
            <strong>Error loading interaction table:</strong> ${frappe.utils.escape_html(err && err.message ? err.message : "API Failure")}
            <button class="btn btn-default btn-xs ml-2 v-btn-retry-table">Retry Table</button>
          </div>
        `);
        $wrap.find(".v-btn-retry-table").on("click", function() { load_interactions(start); });
      }
    });
  }

  function render_interaction_table(res) {
    const rows = res.interactions || [];
    const total = res.total_count || 0;
    const $wrap = root.find("#v-interaction-table-wrap");
    root.find("#v-interaction-count").text(__("Showing {0} to {1} of {2} interactions", [
      total ? current_page_start + 1 : 0,
      Math.min(current_page_start + page_length, total),
      total
    ]));

    if (!rows.length) {
      $wrap.html(`<div class="text-muted p-4 text-center">No customer interactions found for this employee and date range.</div>`);
      return;
    }

    let html = `
      <table class="visa-table">
        <thead>
          <tr>
            <th>${__("Customer / Lead")}</th>
            <th>${__("Date / Time")}</th>
            <th>${__("Channel")}</th>
            <th>${__("Visa / Destination")}</th>
            <th>${__("Outcome")}</th>
            <th>${__("AI Status & Score")}</th>
            <th style="text-align:right;">${__("Actions")}</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map(row => {
            let statusBadge = `<span class="visa-badge-evaluated">${row.ai_score || 0}/100</span>`;
            if (row.ai_status === "Pending") {
              statusBadge = `<span class="visa-badge-pending">AI Pending</span>`;
            } else if (row.ai_status === "Failed") {
              statusBadge = `<span class="visa-badge-failed">AI Failed</span>`;
            } else if (row.ai_status === "Unavailable" || row.ai_score === null) {
              statusBadge = `<span class="visa-badge-insufficient">No AI Data</span>`;
            }

            return `
              <tr class="visa-table-row" data-id="${row.name}">
                <td>
                  <strong>${frappe.utils.escape_html(row.customer_name)}</strong>
                  ${row.phone ? `<div class="text-muted" style="font-size:11px;">📞 ${frappe.utils.escape_html(row.phone)}</div>` : ""}
                  ${row.lead ? `<div class="text-muted" style="font-size:10px;">Lead: ${frappe.utils.escape_html(row.lead)}</div>` : ""}
                </td>
                <td>${frappe.datetime.prettyDate(row.event_datetime)}</td>
                <td>${frappe.utils.escape_html(row.channel)} (${frappe.utils.escape_html(row.direction)})</td>
                <td>${frappe.utils.escape_html(row.visa_type || "N/A")} ${row.country_interested ? `&bull; ${frappe.utils.escape_html(row.country_interested)}` : ""}</td>
                <td><span class="badge badge-info">${frappe.utils.escape_html(row.outcome)}</span></td>
                <td>${statusBadge}</td>
                <td style="text-align:right;">
                  <button class="btn btn-default btn-xs v-btn-view-detail" data-id="${row.name}">${__("Investigate")}</button>
                </td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>

      <div class="visa-pagination">
        <div>${__("Page {0} of {1}", [Math.floor(current_page_start / page_length) + 1, Math.ceil(total / page_length) || 1])}</div>
        <div style="display:flex;gap:8px;">
          <button class="btn btn-default btn-sm" id="v-btn-prev" ${current_page_start <= 0 ? "disabled" : ""}>${__("Previous")}</button>
          <button class="btn btn-default btn-sm" id="v-btn-next" ${current_page_start + page_length >= total ? "disabled" : ""}>${__("Next")}</button>
        </div>
      </div>`;

    $wrap.html(html);

    $wrap.find(".visa-table-row, .v-btn-view-detail").on("click", function (e) {
      e.stopPropagation();
      const id = $(this).data("id");
      if (id) open_drilldown_dialog(id);
    });

    $wrap.find("#v-btn-prev").on("click", function () {
      if (current_page_start > 0) {
        load_interactions(current_page_start - page_length);
      }
    });

    $wrap.find("#v-btn-next").on("click", function () {
      if (current_page_start + page_length < res.total_count) {
        load_interactions(current_page_start + page_length);
      }
    });
  }

  function open_drilldown_dialog(comm_name) {
    frappe.call({
      method: "visa_crm.api.dashboard.employee_interaction_detail",
      args: { communication_event: comm_name },
      callback: function (r) {
        const detail = r.message || {};
        const comm = detail.communication_event || {};
        const lead = detail.lead || {};
        const cust = detail.customer || {};
        const visa = detail.visa_application || {};
        const ev = detail.employee_evaluation || {};
        const todos = detail.todos || [];
        const qinfo = detail.queue_info || {};

        let contentHtml = `
          <div style="font-family:system-ui,sans-serif;font-size:13px;line-height:1.5;">
            <div style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap;">
              ${comm.name ? `<a href="/app/communication-event/${comm.name}" target="_blank" class="btn btn-default btn-xs">Communication Event: ${comm.name}</a>` : ""}
              ${cust.name ? `<a href="/app/customer/${cust.name}" target="_blank" class="btn btn-default btn-xs">Customer: ${cust.customer_name || cust.name}</a>` : ""}
              ${lead.name ? `<a href="/app/crm-lead/${lead.name}" target="_blank" class="btn btn-default btn-xs">CRM Lead: ${lead.name}</a>` : ""}
              ${visa.name ? `<a href="/app/visa-application/${visa.name}" target="_blank" class="btn btn-default btn-xs">Visa Application: ${visa.name}</a>` : ""}
              ${ev.name ? `<a href="/app/employee-evaluation/${ev.name}" target="_blank" class="btn btn-default btn-xs">AI Evaluation: ${ev.name}</a>` : ""}
            </div>

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;">
              <div style="background:#f7fafc;padding:12px;border-radius:6px;border:1px solid #e2e8f0;">
                <h5 style="margin:0 0 8px;font-size:14px;color:#2b6cb0;">Interaction Overview</h5>
                <div><strong>Channel:</strong> ${comm.source || comm.event_type || "N/A"} (${comm.direction || "Inbound"})</div>
                <div><strong>Date/Time:</strong> ${comm.event_datetime || comm.creation}</div>
                <div><strong>Phone:</strong> ${cust.mobile_no || lead.mobile_no || comm.phone || "N/A"}</div>
                <div><strong>Email:</strong> ${cust.email_id || lead.email || comm.email || "N/A"}</div>
                <div><strong>Lead Status:</strong> <span class="badge badge-info">${lead.status || comm.status || "Open"}</span></div>
              </div>

              <div style="background:#f7fafc;padding:12px;border-radius:6px;border:1px solid #e2e8f0;">
                <h5 style="margin:0 0 8px;font-size:14px;color:#2b6cb0;">AI Evaluation & Ratings</h5>
                <div><strong>Overall Score:</strong> ${ev.overall_score !== undefined ? `${ev.overall_score}/100` : (comm.ai_score !== undefined ? `${comm.ai_score}/100` : "No Evaluation")}</div>
                <div><strong>Friendliness:</strong> ${ev.friendliness || "N/A"}</div>
                <div><strong>Empathy:</strong> ${ev.empathy || "N/A"}</div>
                <div><strong>Professionalism:</strong> ${ev.professionalism || "N/A"}</div>
                <div><strong>Clarity:</strong> ${ev.clarity || "N/A"}</div>
                <div><strong>Policy Compliance:</strong> ${ev.policy_compliance || "N/A"}</div>
              </div>
            </div>`;

        if (ev.ai_feedback || ev.coaching_tips || comm.summary || comm.coaching_suggestion) {
          contentHtml += `
            <div style="background:#ebf8ff;border:1px solid #bee3f8;padding:12px;border-radius:6px;margin-bottom:16px;">
              <h5 style="margin:0 0 6px;color:#2b6cb0;font-size:14px;">💡 AI Summary & Coaching Feedback</h5>
              <p style="margin:0 0 6px;">${frappe.utils.escape_html(comm.summary || ev.ai_feedback || "")}</p>
              ${ev.coaching_tips || comm.coaching_suggestion ? `<div style="font-weight:600;color:#2c5282;">Coaching Suggestion: ${frappe.utils.escape_html(ev.coaching_tips || comm.coaching_suggestion)}</div>` : ""}
            </div>`;
        }

        const aijob = detail.ai_job_info || {};

        if (qinfo.ai_error || qinfo.ai_traceback || aijob.last_error) {
          contentHtml += `
            <div style="background:#fff5f5;border:1px solid #fed7d7;padding:12px;border-radius:6px;margin-bottom:16px;color:#9b2c2c;">
              <h5 style="margin:0 0 6px;color:#e53e3e;font-size:14px;">⚠️ AI Processing Failure Details</h5>
              <div><strong>Status:</strong> ${aijob.state || qinfo.ai_status || "Failed"}</div>
              <div><strong>Error:</strong> ${frappe.utils.escape_html(aijob.last_error || qinfo.ai_error || "Unknown Error")}</div>
            </div>`;
        }

        if (todos && todos.length) {
          contentHtml += `
            <div style="background:#f7fafc;padding:12px;border-radius:6px;border:1px solid #e2e8f0;">
              <h5 style="margin:0 0 8px;font-size:14px;color:#2b6cb0;">Linked Follow-up Tasks</h5>
              ${todos.map(t => `
                <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px;">
                  <span>📌 <a href="/app/todo/${t.name}" target="_blank">${frappe.utils.escape_html(t.description || t.name)}</a></span>
                  <span class="badge ${t.status === "Closed" ? "badge-success" : "badge-warning"}">${t.status}</span>
                </div>
              `).join("")}
            </div>`;
        }

        contentHtml += `</div>`;

        const d = new frappe.ui.Dialog({
          title: __("Interaction Investigation — {0}", [comm_name]),
          size: "large",
          content: contentHtml,
          primary_action_label: __("Close"),
          primary_action: function () {
            d.hide();
          }
        });
        d.show();
      }
    });
  }

  init();
}

frappe.pages["employee-performance-dashboard"].on_page_load = render_employee_performance_dashboard;
frappe.pages["employee-dashboard"].on_page_load = render_employee_performance_dashboard;