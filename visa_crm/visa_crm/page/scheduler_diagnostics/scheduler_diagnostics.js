frappe.pages["scheduler-diagnostics"].on_page_load=function(wrapper){
    const page=frappe.ui.make_app_page({parent:wrapper,title:"Scheduler Diagnostics",single_column:true});
    const root=$(`<div class="visa-prod"><button class="btn btn-primary btn-sm" data-refresh>Refresh</button><pre class="visa-prod-json"></pre></div>`).appendTo(page.body);
    function load(){frappe.call({method:"visa_crm.api.production_diagnostics.scheduler_diagnostics",callback:r=>root.find("pre").text(JSON.stringify(r.message||{},null,2))})}
    root.on("click","[data-refresh]",load);load();
};
