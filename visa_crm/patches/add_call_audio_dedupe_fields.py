import frappe
import hashlib
import os
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils.file_manager import get_file_path

def execute():
    if not frappe.db.exists("DocType", "Call Intelligence"):
        return
    create_custom_fields({"Call Intelligence": [
        {"fieldname": "audio_fingerprint", "label": "Audio Fingerprint", "fieldtype": "Data", "insert_after": "audio_filename", "unique": 1},
        {"fieldname": "duplicate_of", "label": "Duplicate Of", "fieldtype": "Link", "options": "Call Intelligence", "insert_after": "audio_fingerprint"}
    ]}, update=True)
    _backfill()
    frappe.db.commit()

def _backfill():
    if not frappe.get_meta("Call Intelligence").has_field("audio_fingerprint"):
        return
    rows = frappe.get_all("Call Intelligence", fields=["name", "recording_file", "audio_filename", "file_size"], order_by="creation asc", limit=5000)
    seen = {}
    for row in rows:
        key = _key(row)
        if not key:
            continue
        if key in seen:
            _set(row.name, {"duplicate_of": seen[key]})
        else:
            seen[key] = row.name
            _set(row.name, {"audio_fingerprint": key})

def _key(row):
    if row.recording_file:
        try:
            path = get_file_path(row.recording_file)
            if path and os.path.exists(path):
                digest = hashlib.sha256()
                with open(path, "rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                return f"sha256:{digest.hexdigest()}"
        except Exception:
            return row.recording_file[:255]
    if row.audio_filename and row.file_size:
        return f"name-size:{row.audio_filename}:{row.file_size}"[:255]
    return None

def _set(name, values):
    clean = {field: value for field, value in values.items() if frappe.get_meta("Call Intelligence").has_field(field) and value}
    if clean:
        try:
            frappe.db.set_value("Call Intelligence", name, clean, update_modified=False)
        except Exception:
            frappe.logger("visa_crm.migration").warning(f"Skipped Call Intelligence dedupe backfill for {name}: {frappe.get_traceback()}")
