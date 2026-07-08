frappe.pages["communication-center"].on_page_load=function(wrapper){
    const page=frappe.ui.make_app_page({parent:wrapper,title:"Communication Center",single_column:true});
    const state={filters:{status:"Open"},rows:[]};
    const root=$(`<div class="visa-cc"><div class="visa-cc-toolbar"><button class="btn btn-primary btn-sm" data-action="refresh">Refresh</button><select class="form-control input-sm" data-filter="status"><option>Open</option><option>Pending</option><option>Resolved</option><option>Archived</option></select><input class="form-control input-sm" data-filter="search" placeholder="Search"></div><div class="visa-cc-counters"></div><div class="visa-cc-layout"><div class="visa-cc-list"></div><div class="visa-cc-thread"><div class="text-muted">Select a conversation</div></div></div></div>`).appendTo(page.body);
    function load(){
        frappe.call({method:"visa_crm.api.communication_center.shared_inbox",args:{filters:state.filters,limit:80},callback:r=>{state.rows=(r.message||{}).rows||[];render(r.message||{});}});
    }
    function render(data){
        const counters=data.counters||{};
        root.find(".visa-cc-counters").html(`<span>Unread ${counters.unread||0}</span><span>Open ${counters.open||0}</span><span>Pending ${counters.pending||0}</span>`);
        const q=(root.find('[data-filter="search"]').val()||"").toLowerCase();
        const rows=state.rows.filter(x=>!q || [x.content,x.phone,x.email,x.customer,x.lead].join(" ").toLowerCase().includes(q));
        root.find(".visa-cc-list").html(rows.map(row=>`<button class="visa-cc-item ${row.unread?"is-unread":""}" data-name="${row.name}"><b>${frappe.utils.escape_html(row.customer||row.phone||row.email||row.name)}</b><span>${frappe.utils.escape_html(row.source||"")}</span><p>${frappe.utils.escape_html(row.summary||row.content||"")}</p></button>`).join("")||`<div class="text-muted">No conversations</div>`);
    }
    function open(name){
        frappe.call({method:"visa_crm.api.communication_center.conversation",args:{name},callback:r=>{
            const data=r.message||{}, event=data.event||{}, history=data.history||[];
            root.find(".visa-cc-thread").html(`<div class="visa-cc-head"><h4>${frappe.utils.escape_html(event.customer||event.phone||event.email||event.name)}</h4><div><button class="btn btn-sm btn-default" data-thread="${name}" data-action="read">Read</button><button class="btn btn-sm btn-default" data-thread="${name}" data-action="pending">Pending</button><button class="btn btn-sm btn-default" data-thread="${name}" data-action="resolved">Resolve</button></div></div><div class="visa-cc-messages">${history.map(msg=>`<div class="visa-cc-msg ${msg.direction==="Outbound"?"out":""}"><small>${frappe.datetime.str_to_user(msg.event_datetime||"")}</small><p>${frappe.utils.escape_html(msg.content||msg.summary||"")}</p></div>`).join("")}</div><div class="visa-cc-reply"><textarea class="form-control" rows="3" placeholder="Reply or internal note"></textarea><button class="btn btn-primary btn-sm" data-thread="${name}" data-action="note">Save Note</button></div>`);
        }});
    }
    root.on("click",'[data-action="refresh"]',load);
    root.on("change",'[data-filter="status"]',e=>{state.filters.status=e.target.value;load();});
    root.on("input",'[data-filter="search"]',()=>render({counters:{}}));
    root.on("click",".visa-cc-item",e=>open($(e.currentTarget).data("name")));
    root.on("click",'[data-action="read"],[data-action="pending"],[data-action="resolved"],[data-action="note"]',e=>{
        const btn=$(e.currentTarget), action=btn.data("action"), name=btn.data("thread"), args={name};
        if(action==="read") args.mark_read=1;
        if(action==="pending") args.status="Pending";
        if(action==="resolved") args.status="Resolved";
        if(action==="note") args.internal_note=root.find(".visa-cc-reply textarea").val();
        frappe.call({method:"visa_crm.api.communication_center.update_conversation",args,callback:()=>{load();open(name);}});
    });
    load();
};
