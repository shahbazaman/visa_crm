import frappe

def execute():
    if not frappe.db.exists("DocType", "Call Intelligence"):
        return
    _backfill_identity()
    _repair_by_recording_file()
    _repair_by_fingerprint()
    frappe.db.commit()

def _backfill_identity():
    meta = frappe.get_meta("Call Intelligence")
    fields = ["name", "recording_file", "audio_filename", "file_size"]
    rows = frappe.get_all("Call Intelligence", fields=fields, order_by="creation asc", limit=10000)
    for row in rows:
        values = {}
        if row.recording_file and not row.audio_filename and meta.has_field("audio_filename"):
            values["audio_filename"] = row.recording_file.split("/")[-1][:255]
        if values:
            frappe.db.set_value("Call Intelligence", row.name, values, update_modified=False)

def _repair_by_recording_file():
    rows = frappe.db.sql("""
        select recording_file,group_concat(name order by creation asc) names
        from `tabCall Intelligence`
        where ifnull(recording_file,'')!=''
        group by recording_file
        having count(*)>1
    """, as_dict=True)
    for row in rows:
        _mark_duplicates((row.names or "").split(","))

def _repair_by_fingerprint():
    if not frappe.get_meta("Call Intelligence").has_field("audio_fingerprint"):
        return
    rows = frappe.db.sql("""
        select audio_fingerprint,group_concat(name order by creation asc) names
        from `tabCall Intelligence`
        where ifnull(audio_fingerprint,'')!=''
        group by audio_fingerprint
        having count(*)>1
    """, as_dict=True)
    for row in rows:
        _mark_duplicates((row.names or "").split(","))

def _mark_duplicates(names):
    names = [name for name in names if name]
    if len(names) < 2:
        return
    original = names[0]
    for duplicate in names[1:]:
        values = {"processing_status": "Success", "ai_error": f"Duplicate audio skipped; original Call Intelligence: {original}"}
        if frappe.get_meta("Call Intelligence").has_field("duplicate_of"):
            values["duplicate_of"] = original
        frappe.db.set_value("Call Intelligence", duplicate, values, update_modified=False)
