frappe.ui.form.on("Employee KPI",{

refresh(frm){

frm.set_query("employee",function(){

return{

filters:{

status:"Active"

}

}

})

}

})