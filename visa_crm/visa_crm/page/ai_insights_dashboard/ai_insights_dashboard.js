frappe.pages["ai-insights-dashboard"].on_page_load=function(wrapper){
    const page=frappe.ui.make_app_page({parent:wrapper,title:"AI Insights Dashboard",single_column:true});
    const root=$(`<div class="visa-ai"><div class="visa-ai-grid"></div><h4>Recommendations</h4><div class="visa-ai-list"></div></div>`).appendTo(page.body);
    function load(){
        frappe.call({method:"visa_crm.api.ai_intelligence.insights_dashboard",callback:r=>{
            const d=r.message||{}, perf=d.performance||[], sent=d.sentiment||[], rec=d.recommendations||[];
            root.find(".visa-ai-grid").html(`<div><b>${perf.length}</b><span>Employees</span></div><div><b>${rec.length}</b><span>Open AI Actions</span></div><div><b>${sent.length}</b><span>Sentiment Buckets</span></div>`);
            root.find(".visa-ai-list").html(rec.map(x=>`<div class="visa-ai-card"><b>${frappe.utils.escape_html(x.customer||x.lead||x.name)}</b><p>${frappe.utils.escape_html(x.ai_next_best_action||"")}</p><small>Priority ${x.ai_customer_priority||0}</small></div>`).join("")||`<div class="text-muted">No AI recommendations yet</div>`);
        }});
    }
    load();
};
