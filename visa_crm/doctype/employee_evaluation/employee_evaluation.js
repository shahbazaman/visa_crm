frappe.ui.form.on("Employee Evaluation",{

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