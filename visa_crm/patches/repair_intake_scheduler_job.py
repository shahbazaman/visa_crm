import frappe

METHOD="visa_crm.api.intake_processor.process_pending"
CRON="* * * * *"

def execute():
    _ensure_job()
    frappe.db.commit()

def _ensure_job():
    if not frappe.db.exists("DocType","Scheduled Job Type"):
        return
    job=_find_job()
    if not job:
        doc=frappe.new_doc("Scheduled Job Type")
        _set(doc,"method",METHOD)
        _set(doc,"frequency","Cron")
        _set(doc,"cron_format",CRON)
        _set(doc,"stopped",0)
        _set(doc,"disabled",0)
        doc.insert(ignore_permissions=True)
        return
    values={}
    if _has_column("frequency"):
        values["frequency"]="Cron"
    if _has_column("cron_format"):
        values["cron_format"]=CRON
    if _has_column("stopped"):
        values["stopped"]=0
    if _has_column("disabled"):
        values["disabled"]=0
    if values:
        frappe.db.set_value("Scheduled Job Type",job,values,update_modified=False)

def _find_job():
    if _has_column("method"):
        return frappe.db.get_value("Scheduled Job Type",{"method":METHOD},"name")
    return METHOD if frappe.db.exists("Scheduled Job Type",METHOD) else None

def _set(doc,field,value):
    if doc.meta.has_field(field):
        doc.set(field,value)

def _has_column(field):
    try:
        return frappe.db.has_column("Scheduled Job Type",field)
    except Exception:
        return frappe.get_meta("Scheduled Job Type").has_field(field)
