console.log("Manager Dashboard JS Loaded");
frappe.pages["manager-dashboard"].on_page_load=function(wrapper){

const page=frappe.ui.make_app_page({

parent:wrapper,

title:"Manager Dashboard",

single_column:true

})

// page.main.html(frappe.render_template("manager_dashboard"))
page.main.html(`
<h1 style="color:red">
Manager Dashboard Loaded
</h1>
`)
load_dashboard()

}

function load_dashboard(){

frappe.call({

method:"visa_crm.page.manager_dashboard.manager_dashboard.get_dashboard",

callback:function(r){

console.log("Dashboard Data",r)

render_kpis(r.message)

render_leaderboard(r.message)

}

})

}

function render_kpis(data){

let html='<div class="kpi-grid">'

html+=card("Employees",data.overview.employees)

html+=card("Customers",data.overview.customers)

html+=card("Calls",data.overview.calls)

html+=card("Leads",data.overview.leads)

html+='</div>'

$("#kpi-cards").html(html)

}

function card(title,value){

return `

<div class="kpi-card">

<div class="kpi-title">

${title}

</div>

<div class="kpi-value">

${value}

</div>

</div>

`

}

function render_leaderboard(data){

let html=""

html+="<h3>Top Counselors</h3>"

html+="<table class='table table-bordered'>"

html+="<thead>"

html+="<tr>"

html+="<th>Employee</th>"

html+="<th>Total Calls</th>"

html+="<th>Total Leads</th>"

html+="<th>Converted</th>"

html+="<th>Avg Lead Score</th>"

html+="<th>Avg Evaluation</th>"

html+="</tr>"

html+="</thead><tbody>"

data.employees.forEach(function(d){

html+="<tr>"

html+=`<td>${d.employee||""}</td>`

html+=`<td>${d.total_calls||0}</td>`

html+=`<td>${d.total_leads||0}</td>`

html+=`<td>${d.converted_leads||0}</td>`

html+=`<td>${Number(d.average_lead_score||0).toFixed(2)}</td>`

html+=`<td>${Number(d.average_evaluation_score||0).toFixed(2)}</td>`

html+="</tr>"

})

html+="</tbody></table>"

$("#leaderboard").html(html)

}