frappe.ui.form.on('Communication Event', {

refresh(frm){

frm.set_query("customer",function(){

return {
filters:{
disabled:0
}
}

})


frm.set_query("employee",function(){

return{
filters:{
status:"Active"
}
}

})


}


})
