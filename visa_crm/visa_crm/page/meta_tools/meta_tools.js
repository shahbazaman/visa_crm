frappe.pages["meta-tools"].on_page_load=function(wrapper){
    const page=frappe.ui.make_app_page({parent:wrapper,title:"Meta Tools",single_column:true});
    const root=$(`<div class="visa-prod"><div class="input-group" style="max-width:620px"><input class="form-control" data-lead placeholder="leadgen_id"><button class="btn btn-secondary" data-preview>Preview</button><button class="btn btn-primary" data-run>Process Real Lead</button></div><pre class="visa-prod-json" style="margin-top:16px"></pre></div>`).appendTo(page.body);
    function show(r){root.find("pre").text(JSON.stringify(r.message||r,null,2))}
    root.on("click","[data-preview]",()=>frappe.call({method:"visa_crm.api.meta_pipeline_audit.graph_preview",args:{leadgen_id:root.find("[data-lead]").val()},callback:show}));
    root.on("click","[data-run]",()=>frappe.call({method:"visa_crm.api.meta_pipeline_audit.process_real_lead",args:{leadgen_id:root.find("[data-lead]").val()},callback:show}));
};
