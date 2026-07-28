frappe.pages["intake-pipeline"].on_page_load=function(wrapper){
    const page=frappe.ui.make_app_page({parent:wrapper,title:"Lead Intake Pipeline",single_column:true});
    const root=$(`<div class="visa-prod"><button class="btn btn-primary btn-sm" data-refresh>Refresh</button><div class="visa-pipeline"></div></div>`).appendTo(page.body);
    function dot(s){return `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${s==="green"?"#16a34a":s==="red"?"#dc2626":"#f59e0b"}"></span>`}
    function row(x){return `<div class="visa-card"><b>${frappe.utils.escape_html(x.queue||"")}</b><div>${frappe.utils.escape_html(x.status||"")}</div><div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:8px">${(x.timeline||[]).map(t=>`<span>${dot(t.state)} ${frappe.utils.escape_html(t.stage)}</span>`).join("")}</div><pre>${frappe.utils.escape_html(JSON.stringify(x,null,2))}</pre></div>`}
    function load(){frappe.call({method:"visa_crm.api.meta_pipeline_audit.intake_pipeline",callback:r=>root.find(".visa-pipeline").html((r.message||[]).map(row).join("")||"<p>No queue records.</p>")})}
    root.on("click","[data-refresh]",load);load();
};
