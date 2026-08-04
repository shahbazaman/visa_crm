frappe.ui.form.on("Email Account",{
    refresh(frm){
        if(frm.is_new()) return;
        frm.add_custom_button(__("Diagnose Email Account"),()=>{
            frappe.call({
                method:"visa_crm.api.email_account.diagnose_email_account",
                args:{email_account:frm.doc.name,direction:"both"},
                freeze:true,
                freeze_message:__("Testing incoming and outgoing email connections..."),
                callback:r=>show_email_diagnostics(r.message||{})
            });
        },__("Actions"));
    }
});

function show_email_diagnostics(data){
    const esc=frappe.utils.escape_html;
    const rows=Object.entries(data.results||{}).map(([direction,result])=>`<tr><td>${esc(__(direction))}</td><td>${result.ok?__("Connected"):esc(__(result.category||"Failed"))}</td><td>${esc(result.message||"")}</td></tr>`).join("");
    const oauth=data.oauth&&data.oauth.status!=="not_applicable"?`<p><b>${__("OAuth")}</b>: ${esc(__(data.oauth.status||"unknown"))}</p>`:"";
    frappe.msgprint({title:__("Email Diagnostics"),indicator:Object.values(data.results||{}).every(x=>x.ok)?"green":"orange",message:`${oauth}<div class="table-responsive"><table class="table table-bordered"><thead><tr><th>${__("Direction")}</th><th>${__("Status")}</th><th>${__("Details")}</th></tr></thead><tbody>${rows}</tbody></table></div>`});
}
