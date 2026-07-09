frappe.pages["meta-diagnostics"].on_page_load=function(wrapper){
    const page=frappe.ui.make_app_page({parent:wrapper,title:"Meta Diagnostics",single_column:true});
    const root=$(`<div class="visa-prod"><div class="visa-cc-toolbar"><input class="form-control input-sm" placeholder="leadgen_id"><button class="btn btn-primary btn-sm" data-fetch>Fetch Lead</button><button class="btn btn-default btn-sm" data-refresh>Refresh</button></div><pre class="visa-prod-json"></pre></div>`).appendTo(page.body);
    function load(id){frappe.call({method:"visa_crm.api.production_diagnostics.meta_diagnostics",args:{leadgen_id:id||""},callback:r=>root.find("pre").text(JSON.stringify(r.message||{},null,2))})}
    root.on("click","[data-refresh]",()=>load());root.on("click","[data-fetch]",()=>load(root.find("input").val()));load();
};
