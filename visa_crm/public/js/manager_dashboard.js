frappe.pages["manager-dashboard"] = frappe.pages["manager-dashboard"] || {};

frappe.pages["manager-dashboard"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: "Manager Dashboard",
    single_column: true,
  });

  const root = $('<div class="visa-manager-dashboard"></div>').appendTo(page.body);

  if (!document.getElementById("visa-manager-dashboard-style")) {
    $("head").append(`<style id="visa-manager-dashboard-style">
      .visa-manager-dashboard { padding: 16px 0 32px; }
      .visa-kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }
      .visa-kpi { border: 1px solid var(--border-color); border-radius: 8px; padding: 14px; background: var(--card-bg); }
      .visa-kpi-label { color: var(--text-muted); font-size: 12px; margin-bottom: 6px; }
      .visa-kpi-value { font-size: 26px; font-weight: 650; line-height: 1.1; }
      .visa-panel { margin-top: 16px; border: 1px solid var(--border-color); border-radius: 8px; background: var(--card-bg); padding: 14px; }
      .visa-panel h3 { font-size: 15px; margin: 0 0 12px; }
      .visa-muted { color: var(--text-muted); }
    </style>`);
  }

  root.html('<div class="visa-muted">Loading dashboard...</div>');

  frappe.call({
    method: "visa_crm.api.dashboard.manager_kpis",
    callback: function (r) {
      const data = r.message || {};
      const labels = [
        ["customers", "Customers"],
        ["leads", "Leads"],
        ["calls", "Calls"],
        ["communication_events", "Communication Events"],
        ["todos", "Open Tasks"],
        ["hot_leads", "Hot Leads"],
        ["medium_leads", "Medium Leads"],
        ["cold_leads", "Cold Leads"],
      ];

      root.html(`
        <div class="visa-kpi-grid">
          ${labels.map(([key, label]) => `
            <div class="visa-kpi">
              <div class="visa-kpi-label">${frappe.utils.escape_html(label)}</div>
              <div class="visa-kpi-value">${frappe.utils.escape_html(String(data[key] ?? 0))}</div>
            </div>
          `).join("")}
        </div>
        <div class="visa-panel">
          <h3>Operational Snapshot</h3>
          <div class="visa-muted">Dashboard loaded successfully.</div>
        </div>
      `);
    },
    error: function () {
      root.html('<div class="visa-panel">Unable to load dashboard metrics. Check Error Log.</div>');
    },
  });
};