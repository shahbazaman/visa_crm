import frappe
from visa_crm.api.meta_utils import has_doctype, has_field
from visa_crm.www.visa_portal import _customer

no_cache=1

def get_context(context):
    context.customer=_customer()
    context.title="Upload Document"
    return context

@frappe.whitelist()
def register_document(document_name=None,file_url=None,visa_application=None):
    customer=_customer()
    if not has_doctype("Customer Documents"):
        frappe.throw("Document management is not enabled.")
    if file_url and not str(file_url).startswith(("/files/","/private/files/")):
        frappe.throw("Invalid uploaded file path.")
    doc=frappe.new_doc("Customer Documents")
    _set(doc,"customer",customer)
    _set(doc,"document_name",document_name or "Customer Upload")
    _set(doc,"document_type",document_name or "Customer Upload")
    _set(doc,"file",file_url)
    _set(doc,"document_file",file_url)
    _set(doc,"visa_application",visa_application)
    _set(doc,"status","Received")
    _set(doc,"verification_status","Pending")
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name

def _set(doc,field,value):
    if value is not None and has_field(doc.doctype,field):
        doc.set(field,value)
