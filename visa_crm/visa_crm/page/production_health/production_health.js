frappe.pages["production-health"].on_page_load=function(wrapper){
    const page=frappe.ui.make_app_page({parent:wrapper,title:"Production Health",single_column:true});
    const root=$(`<div class="visa-prod"><button class="btn btn-primary btn-sm" data-refresh>Refresh</button><div class="visa-prod-grid"></div><pre class="visa-prod-json"></pre></div>`).appendTo(page.body);
    function badge(label,value){return `<div class="visa-card"><b>${frappe.utils.escape_html(label)}</b><span class="${value?'text-success':'text-danger'}">${value?"PASS":"FAIL"}</span></div>`}
    function load(){frappe.call({method:"visa_crm.api.production_diagnostics.production_health",callback:r=>{const d=r.message||{};root.find(".visa-prod-grid").html([badge("Scheduler running",d.scheduler_running),badge("Webhook today",d.webhook_received_today),badge("Meta API",d.meta_api_status==="configured"),badge("Gemini",d.gemini_status==="configured"),`<div class="visa-card"><b>Queue waiting</b><span>${d.queue_waiting||0}</span></div>`,`<div class="visa-card"><b>Queue failed</b><span>${d.queue_failed||0}</span></div>`,`<div class="visa-card"><b>Queue processed</b><span>${d.queue_processed||0}</span></div>`].join(""));root.find(".visa-prod-json").text(JSON.stringify(d,null,2));}})}
    root.on("click","[data-refresh]",load);load();
};
