frappe.pages["manager-dashboard"].on_page_load=function(wrapper){

const page=frappe.ui.make_app_page({

parent:wrapper,

title:"Manager Dashboard",

single_column:true

})

page.main.html(frappe.render_template("manager_dashboard"))

load_dashboard()

}

function load_dashboard(){

frappe.call({

method:"visa_crm.page.manager_dashboard.manager_dashboard.get_dashboard",

callback:function(r){

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

html+="<th>Score</th>"

html+="<th>Conversion</th>"

html+="<th>Response</th>"

html+="</tr>"

html+="</thead><tbody>"

data.employees.forEach(function(d){

html+="<tr>"

html+=`<td>${d.employee}</td>`

html+=`<td>${Number(d.score).toFixed(2)}</td>`

html+=`<td>${Number(d.conversion).toFixed(2)}</td>`

html+=`<td>${Number(d.response).toFixed(2)}</td>`

html+="</tr>"

})

html+="</tbody></table>"

$("#leaderboard").html(html)

}

