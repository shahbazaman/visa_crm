frappe.ui.form.on("Lead Assignment",{

refresh(frm){

frm.set_query("assigned_to",function(){

return{
filters:{
status:"Active"
}
}

})

}

})