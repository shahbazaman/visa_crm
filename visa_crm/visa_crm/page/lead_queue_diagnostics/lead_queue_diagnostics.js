frappe.pages["lead-queue-diagnostics"].on_page_load=function(wrapper){
    const page=frappe.ui.make_app_page({parent:wrapper,title:"Lead Queue Diagnostics",single_column:true});
    const root=$(`<div class="visa-prod"><button class="btn btn-primary btn-sm" data-refresh>Refresh</button><div class="visa-table-wrap"><table class="table table-bordered"><thead><tr><th>Queue</th><th>Stage</th><th>Retry</th><th>Lead ID</th><th>Scheduler</th><th>Duration</th><th>Failure</th></tr></thead><tbody></tbody></table></div></div>`).appendTo(page.body);
    function load(){frappe.call({method:"visa_crm.api.production_diagnostics.queue_diagnostics",callback:r=>{const rows=r.message||[];root.find("tbody").html(rows.map(x=>`<tr><td>${frappe.utils.escape_html(x.name||"")}</td><td>${frappe.utils.escape_html(x.current_stage||"")}</td><td>${x.retry_count||0}</td><td>${frappe.utils.escape_html(x.graph_api_request||"")}</td><td>${frappe.utils.escape_html(x.scheduler_timestamp||"")}</td><td>${x.processing_duration||""}</td><td>${frappe.utils.escape_html(x.failure_reason||"")}</td></tr>`).join("")||`<tr><td colspan="7">No queue records</td></tr>`);}})}
    root.on("click","[data-refresh]",load);load();
};
