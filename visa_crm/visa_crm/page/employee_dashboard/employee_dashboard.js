frappe.pages["employee-dashboard"] = frappe.pages["employee-dashboard"] || {};

frappe.pages["employee-dashboard"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: "Employee Performance & AI Dashboard",
    single_column: true,
  });

  const root = $('<div class="visa-employee-dashboard"></div>').appendTo(page.body);

  if (!document.getElementById("visa-employee-dashboard-style")) {
    $("head").append(`<style id="visa-employee-dashboard-style">
      .visa-employee-dashboard { padding: 16px 20px 40px; max-width: 1200px; margin: 0 auto; font-family: var(--font-stack, system-ui, sans-serif); }
      .visa-filter-bar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; background: var(--card-bg, #fff); border: 1px solid var(--border-color, #e2e8f0); padding: 12px 16px; border-radius: 8px; margin-bottom: 20px; }
      .visa-filter-group { display: flex; flex-direction: column; gap: 4px; font-size: 11px; font-weight: 600; color: var(--text-muted, #718096); }
      .visa-filter-group select, .visa-filter-group input { height: 32px; padding: 4px 8px; font-size: 12px; border-radius: 6px; border: 1px solid var(--border-color, #cbd5e0); background: var(--control-bg, #fff); }
      .visa-section-title { font-size: 16px; font-weight: 700; margin: 24px 0 12px; color: var(--heading-color, #1a202c); display: flex; align-items: center; gap: 8px; }
      .visa-kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 20px; }
      .visa-kpi { border: 1px solid var(--border-color, #e2e8f0); border-radius: 10px; padding: 16px; background: var(--card-bg, #fff); transition: box-shadow 0.15s ease; }
      .visa-kpi:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
      .visa-kpi-label { color: var(--text-muted, #718096); font-size: 12px; font-weight: 500; margin-bottom: 6px; }
      .visa-kpi-value { font-size: 28px; font-weight: 700; line-height: 1.1; color: var(--text-color, #1a202c); }
      .visa-kpi-sub { font-size: 11px; color: var(--text-muted, #a0aec0); margin-top: 4px; }
      .visa-badge-insufficient { display: inline-block; padding: 2px 6px; border-radius: 4px; background: #feebc8; color: #744210; font-size: 10px; font-weight: 600; margin-left: 6px; }
      .visa-grid-two { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
      @media(max-width:768px) { .visa-grid-two { grid-template-columns: 1fr; } }
      .visa-panel { border: 1px solid var(--border-color, #e2e8f0); border-radius: 10px; background: var(--card-bg, #fff); padding: 18px; margin-bottom: 20px; }
      .visa-panel-header { font-size: 15px; font-weight: 600; margin-bottom: 14px; color: var(--text-color, #1a202c); border-bottom: 1px solid var(--border-color, #edf2f7); padding-bottom: 8px; }
      .visa-progress-row { margin-bottom: 10px; }
      .visa-progress-label { display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px; }
      .visa-progress-bar-wrap { height: 8px; background: #edf2f7; border-radius: 4px; overflow: hidden; }
      .visa-progress-fill { height: 100%; background: #3182ce; border-radius: 4px; transition: width 0.3s ease; }
      .visa-progress-fill-green { background: #38a169; }
      .visa-progress-fill-purple { background: #805ad5; }
      .visa-progress-fill-orange { background: #dd6b20; }
      .visa-table { width: 100%; border-collapse: collapse; font-size: 13px; }
      .visa-table th, .visa-table td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border-color, #edf2f7); }
      .visa-table th { background: var(--control-bg, #f7fafc); font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-muted, #718096); }
      .visa-coaching-box { background: #ebf8ff; border: 1px solid #bee3f8; border-radius: 8px; padding: 12px 16px; color: #2b6cb0; font-size: 13px; margin-bottom: 8px; }
    </style>`);
  }

  let filters = {
    employee: "",
    from_date: "",
    to_date: "",
    lead_source: "",
    category: "",
    subcategory: ""
  };

  function load_dashboard() {
    root.html('<div class="text-muted p-4">Loading performance metrics...</div>');

    frappe.call({
      method: "visa_crm.api.dashboard.employee_performance_dashboard",
      args: filters,
      callback: function (r) {
        const data = r.message || {};
        render_dashboard(data);
      },
      error: function () {
        root.html('<div class="visa-panel text-danger">Unable to load employee performance dashboard. Please check permissions.</div>');
      }
    });
  }

  function render_dashboard(data) {
    const top = data.top_cards || {};
    const comm = data.communication_performance || {};
    const ai = data.ai_performance || {};
    const rankings = data.rankings || [];
    const health = data.pipeline_health || {};
    const emp = data.employee_info || {};

    let html = `
      <div class="visa-filter-bar">
        <div class="visa-filter-group">
          <label>${__("Counselor / Employee")}</label>
          <input type="text" id="v-emp-filter" class="form-control" placeholder="${__("Employee ID / Name")}" value="${emp.name || filters.employee || ""}" />
        </div>
        <div class="visa-filter-group">
          <label>${__("From Date")}</label>
          <input type="date" id="v-from-date" class="form-control" value="${filters.from_date || ""}" />
        </div>
        <div class="visa-filter-group">
          <label>${__("To Date")}</label>
          <input type="date" id="v-to-date" class="form-control" value="${filters.to_date || ""}" />
        </div>
        <div class="visa-filter-group">
          <label>${__("Lead Source")}</label>
          <select id="v-source-filter" class="form-control">
            <option value="">${__("All Sources")}</option>
            <option value="Meta"${filters.lead_source === "Meta" ? " selected" : ""}>Meta Ads</option>
            <option value="WhatsApp"${filters.lead_source === "WhatsApp" ? " selected" : ""}>WhatsApp</option>
            <option value="Phone"${filters.lead_source === "Phone" ? " selected" : ""}>Phone</option>
            <option value="Google Ads"${filters.lead_source === "Google Ads" ? " selected" : ""}>Google Ads</option>
          </select>
        </div>
        <div class="visa-filter-group" style="margin-left:auto;align-self:flex-end;">
          <button class="btn btn-primary btn-sm" id="v-btn-filter">${__("Apply Filters")}</button>
          <button class="btn btn-default btn-sm" id="v-btn-reset">${__("Reset")}</button>
        </div>
      </div>`;

    if (emp.employee_name) {
      html += `
        <div class="visa-panel">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div>
              <h3 style="margin:0;font-size:18px;">${frappe.utils.escape_html(emp.employee_name)}</h3>
              <span class="text-muted" font-size:12px;>${frappe.utils.escape_html(emp.designation || "Counselor")} &bull; ${frappe.utils.escape_html(emp.department || "Sales")}</span>
            </div>
            <span class="badge badge-success">${frappe.utils.escape_html(emp.status || "Active")}</span>
          </div>
        </div>`;
    }

    html += `
      <div class="visa-section-title">📊 ${__("Lead & Conversion Funnel")}</div>
      <div class="visa-kpi-grid">
        <div class="visa-kpi"><div class="visa-kpi-label">${__("Total Assigned")}</div><div class="visa-kpi-value">${top.total_leads || 0}</div></div>
        <div class="visa-kpi"><div class="visa-kpi-label">${__("New Leads")}</div><div class="visa-kpi-value">${top.new_leads || 0}</div></div>
        <div class="visa-kpi"><div class="visa-kpi-label">${__("Active Leads")}</div><div class="visa-kpi-value">${top.active_leads || 0}</div></div>
        <div class="visa-kpi"><div class="visa-kpi-label">${__("Converted Leads")}</div><div class="visa-kpi-value" style="color:#276749;">${top.converted_leads || 0}</div></div>
        <div class="visa-kpi"><div class="visa-kpi-label">${__("Conversion Rate")}</div><div class="visa-kpi-value" style="color:#2b6cb0;">${top.conversion_rate || 0}%</div></div>
        <div class="visa-kpi"><div class="visa-kpi-label">${__("Lead-to-Deal %")}</div><div class="visa-kpi-value">${top.lead_to_deal_rate || 0}%</div></div>
        <div class="visa-kpi"><div class="visa-kpi-label">${__("Visa Completion %")}</div><div class="visa-kpi-value">${top.visa_completion_rate || 0}%</div></div>
      </div>

      <div class="visa-grid-two">
        <div class="visa-panel">
          <div class="visa-panel-header">📞 ${__("Communication & Task Efficiency")}</div>
          <div class="visa-progress-row">
            <div class="visa-progress-label"><span>${__("Total Calls")}</span><strong>${comm.total_calls || 0}</strong></div>
          </div>
          <div class="visa-progress-row">
            <div class="visa-progress-label"><span>${__("Total Chats & Emails")}</span><strong>${(comm.total_chats || 0) + (comm.total_emails || 0)}</strong></div>
          </div>
          <div class="visa-progress-row">
            <div class="visa-progress-label"><span>${__("Follow-up Compliance")}</span><strong>${comm.followup_compliance || 100}%</strong></div>
            <div class="visa-progress-bar-wrap"><div class="visa-progress-fill visa-progress-fill-green" style="width:${comm.followup_compliance || 100}%;"></div></div>
          </div>
          <div class="visa-progress-row" style="margin-top:12px;">
            <div class="visa-progress-label"><span>${__("Open Follow-ups")}</span><strong>${comm.open_todos || 0}</strong></div>
          </div>
          <div class="visa-progress-row">
            <div class="visa-progress-label"><span>${__("Overdue Tasks")}</span><strong style="color:#c53030;">${comm.overdue_todos || 0}</strong></div>
          </div>
        </div>

        <div class="visa-panel">
          <div class="visa-panel-header">
            🧠 ${__("AI Quality & Intelligence Score")}
            ${ai.insufficient_data ? `<span class="visa-badge-insufficient">${__("Insufficient Data")}</span>` : ""}
          </div>
          <div style="display:flex;align-items:center;gap:16px;margin-bottom:16px;">
            <div style="font-size:36px;font-weight:700;color:#2b6cb0;">${ai.overall_score || 0}<span style="font-size:14px;color:#718096;">/100</span></div>
            <div class="text-muted" style="font-size:12px;">${__("Based on {0} AI evaluations", [ai.evaluations_count || 0])}</div>
          </div>
          <div class="visa-progress-row">
            <div class="visa-progress-label"><span>${__("Friendliness")}</span><span>${ai.friendliness || 0}</span></div>
            <div class="visa-progress-bar-wrap"><div class="visa-progress-fill" style="width:${ai.friendliness || 0}%;"></div></div>
          </div>
          <div class="visa-progress-row">
            <div class="visa-progress-label"><span>${__("Empathy & Active Listening")}</span><span>${ai.empathy || 0}</span></div>
            <div class="visa-progress-bar-wrap"><div class="visa-progress-fill visa-progress-fill-purple" style="width:${ai.empathy || 0}%;"></div></div>
          </div>
          <div class="visa-progress-row">
            <div class="visa-progress-label"><span>${__("Professionalism & Clarity")}</span><span>${ai.professionalism || 0}</span></div>
            <div class="visa-progress-bar-wrap"><div class="visa-progress-fill visa-progress-fill-green" style="width:${ai.professionalism || 0}%;"></div></div>
          </div>
        </div>
      </div>`;

    if (ai.coaching_tips && ai.coaching_tips.length) {
      html += `
        <div class="visa-panel">
          <div class="visa-panel-header">💡 ${__("AI Coaching Recommendations")}</div>
          ${ai.coaching_tips.map(tip => `<div class="visa-coaching-box">📌 ${frappe.utils.escape_html(tip)}</div>`).join("")}
        </div>`;
    }

    if (rankings.length) {
      html += `
        <div class="visa-panel">
          <div class="visa-panel-header">🏆 ${__("Counselor Leaderboard & Performance Ranking")}</div>
          <table class="visa-table">
            <thead>
              <tr>
                <th>${__("Rank")}</th>
                <th>${__("Counselor")}</th>
                <th>${__("Assigned Leads")}</th>
                <th>${__("Converted")}</th>
                <th>${__("Conversion %")}</th>
                <th>${__("AI Score")}</th>
                <th>${__("Status")}</th>
              </tr>
            </thead>
            <tbody>
              ${rankings.map(r => `
                <tr>
                  <td><strong>#${r.rank}</strong></td>
                  <td>${frappe.utils.escape_html(r.employee_name)} <span class="text-muted">(${frappe.utils.escape_html(r.employee)})</span></td>
                  <td>${r.assigned_leads}</td>
                  <td><strong>${r.converted_leads}</strong></td>
                  <td>${r.conversion_rate}%</td>
                  <td>${r.ai_score || 0}</td>
                  <td>${r.insufficient_data ? `<span class="visa-badge-insufficient">${__("Insufficient Data")}</span>` : `<span class="badge badge-success">${__("Active")}</span>`}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>`;
    }

    if (health.total_queues) {
      html += `
        <div class="visa-panel">
          <div class="visa-panel-header">⚙ ${__("Pipeline Operational Health")}</div>
          <div class="visa-kpi-grid" style="margin:0;">
            <div class="visa-kpi"><div class="visa-kpi-label">${__("Total Lead Queues")}</div><div class="visa-kpi-value">${health.total_queues}</div></div>
            <div class="visa-kpi"><div class="visa-kpi-label">${__("Action Required")}</div><div class="visa-kpi-value" style="color:#dd6b20;">${health.action_required || 0}</div></div>
            <div class="visa-kpi"><div class="visa-kpi-label">${__("Uncategorized Leads")}</div><div class="visa-kpi-value" style="color:#e53e3e;">${health.uncategorized_leads || 0}</div></div>
            <div class="visa-kpi"><div class="visa-kpi-label">${__("Failed Stages")}</div><div class="visa-kpi-value">${health.failed_stages || 0}</div></div>
          </div>
        </div>`;
    }

    root.html(html);

    root.find("#v-btn-filter").on("click", function () {
      filters.employee = root.find("#v-emp-filter").val().trim();
      filters.from_date = root.find("#v-from-date").val();
      filters.to_date = root.find("#v-to-date").val();
      filters.lead_source = root.find("#v-source-filter").val();
      load_dashboard();
    });

    root.find("#v-btn-reset").on("click", function () {
      filters = { employee: "", from_date: "", to_date: "", lead_source: "", category: "", subcategory: "" };
      load_dashboard();
    });
  }

  load_dashboard();
};