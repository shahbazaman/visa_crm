frappe.ui.form.on('Call Intelligence', {

refresh(frm){

frm.set_indicator_formatter('processing_status',function(doc){

if(doc.processing_status=="Success")

return "green"


if(doc.processing_status=="Pending")

return "orange"


return "red"

})


}


})
