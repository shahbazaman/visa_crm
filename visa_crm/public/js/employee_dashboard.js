frappe.pages["employee-dashboard"] = frappe.pages["employee-dashboard"] || {};

frappe.pages["employee-dashboard"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: "Employee Dashboard",
    single_column: true,
  });

  const root = $('<div class="visa-employee-dashboard"></div>').appendTo(page.body);

  if (!document.getElementById("visa-employee-dashboard-style")) {
    $("head").append(`<style id="visa-employee-dashboard-style">
      .visa-employee-dashboard { padding: 16px 0 32px; }
      .visa-kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }
      .visa-kpi { border: 1px solid var(--border-color); border-radius: 8px; padding: 14px; background: var(--card-bg); }
      .visa-kpi-label { color: var(--text-muted); font-size: 12px; margin-bottom: 6px; }
      .visa-kpi-value { font-size: 26px; font-weight: 650; line-height: 1.1; }
      .visa-panel { margin-top: 16px; border: 1px solid var(--border-color); border-radius: 8px; background: var(--card-bg); padding: 14px; }
      .visa-muted { color: var(--text-muted); }
    </style>`);
  }

  root.html(`
    <div class="visa-kpi-grid">
      <div class="visa-kpi"><div class="visa-kpi-label">Calls</div><div class="visa-kpi-value">0</div></div>
      <div class="visa-kpi"><div class="visa-kpi-label">Open Follow-ups</div><div class="visa-kpi-value">0</div></div>
      <div class="visa-kpi"><div class="visa-kpi-label">Average Score</div><div class="visa-kpi-value">0</div></div>
      <div class="visa-kpi"><div class="visa-kpi-label">Hot Leads</div><div class="visa-kpi-value">0</div></div>
    </div>
    <div class="visa-panel">
      <div class="visa-muted">Employee Dashboard loaded successfully.</div>
    </div>
  `);
};