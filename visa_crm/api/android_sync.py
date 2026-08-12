import hashlib
import json
import os
import re
import frappe
from frappe.utils import add_to_date, cint, get_datetime, now_datetime
from frappe.utils.file_manager import save_file, get_file_path
from visa_crm.api.meta_utils import has_field, safe_json_dumps
from visa_crm.api.android_metadata import _normalize, validate_metadata, extract_metadata, enrich_audio_file, AUDIO_EXTENSIONS, METADATA_SUFFIX, _recording_prefix

@frappe.whitelist()
def check_call_status(recording_id=None, file_name=None, sha256=None):
    """
    Pre-flight status check endpoint for Android CallSyncWorker.
    Allows client to check if audio or metadata was already received remotely.
    """
    recording_id = (recording_id or "").strip()
    file_name = (file_name or "").strip()
    sha256 = (sha256 or "").strip().replace("sha256:", "")

    file_doc = None
    if file_name:
        file_doc = _find_file_by_name(file_name)
    if not file_doc and recording_id:
        file_doc = _find_file_by_recording_id(recording_id)
    if not file_doc and sha256:
        file_doc = _find_file_by_sha256(sha256)

    call_name = None
    if recording_id and frappe.db.exists("DocType", "Call Intelligence"):
        if frappe.get_meta("Call Intelligence").has_field("recording_id"):
            call_name = frappe.db.get_value("Call Intelligence", {"recording_id": recording_id}, "name")
    if not call_name and file_doc:
        call_name = frappe.db.get_value("Call Intelligence", {"recording_file": file_doc.file_url}, "name")

    return {
        "ok": True,
        "recording_id": recording_id,
        "audio_uploaded": bool(file_doc),
        "recording_file_url": file_doc.file_url if file_doc else None,
        "file_name_doc": file_doc.name if file_doc else None,
        "call_intelligence_created": bool(call_name),
        "call_intelligence_name": call_name,
        "status": "COMPLETED" if call_name else ("AUDIO_UPLOADED" if file_doc else "NOT_FOUND")
    }


@frappe.whitelist()
def upload_call_audio(recording_id=None, filename=None, sha256=None, filedata=None):
    """
    Idempotent audio uploader endpoint.
    If a File with the same file_name, recording_id, or sha256 already exists,
    returns the existing File record without creating duplicate entries in tabFile.
    """
    recording_id = (recording_id or "").strip()
    filename = (filename or getattr(frappe.request, "filename", None) or "").strip()
    sha256 = (sha256 or "").strip().replace("sha256:", "")

    prefix = _recording_prefix(filename) or recording_id

    # 1. Check existing File record
    existing_file = None
    if prefix:
        existing_file = _find_file_by_recording_id(prefix)
    if not existing_file and filename:
        existing_file = _find_file_by_name(filename)
    if not existing_file and sha256:
        existing_file = _find_file_by_sha256(sha256)

    if existing_file:
        return {
            "ok": True,
            "status": "EXISTS",
            "file_name": existing_file.file_name,
            "file_url": existing_file.file_url,
            "file_name_doc": existing_file.name,
            "reused": True
        }

    # 2. Upload file if not existing
    if not filedata and hasattr(frappe.request, "files") and "file" in frappe.request.files:
        uploaded_file = frappe.request.files["file"]
        content = uploaded_file.read()
        filename = filename or uploaded_file.filename
    elif isinstance(filedata, str):
        import base64
        filedata_clean = filedata.strip()
        missing_padding = len(filedata_clean) % 4
        if missing_padding:
            filedata_clean += '=' * (4 - missing_padding)
        content = base64.b64decode(filedata_clean)
    elif isinstance(filedata, bytes):
        content = filedata
    else:
        frappe.throw("No audio file content provided", frappe.ValidationError)

    if not filename:
        frappe.throw("Filename is required for audio upload", frappe.ValidationError)

    saved_file = save_file(filename, content, dt=None, dn=None, is_private=1)
    frappe.db.commit()

    return {
        "ok": True,
        "status": "CREATED",
        "file_name": saved_file.file_name,
        "file_url": saved_file.file_url,
        "file_name_doc": saved_file.name,
        "reused": False
    }


@frappe.whitelist()
def sync_call_metadata(recording_id, metadata_json):
    """
    Idempotent metadata & Call Intelligence pairing endpoint.
    Accepts raw JSON metadata, normalizes INCOMING -> Inbound, OUTGOING -> Outbound,
    and updates/creates Call Intelligence without duplicate records.
    """
    if isinstance(metadata_json, str):
        try:
            metadata_dict = json.loads(metadata_json)
        except Exception as exc:
            frappe.throw(f"Invalid metadata JSON string: {exc}", frappe.ValidationError)
    elif isinstance(metadata_json, dict):
        metadata_dict = metadata_json
    else:
        frappe.throw("metadata_json must be a JSON string or dict", frappe.ValidationError)

    normalized = _normalize(dict(metadata_dict or {}))
    recording_id = normalized.get("recording_id") or recording_id

    if not recording_id:
        frappe.throw("recording_id is required for call metadata sync", frappe.ValidationError)

    # Find matching audio File record
    file_doc = _find_file_by_recording_id(recording_id)

    # Create companion metadata File record if file_doc exists
    meta_filename = f"{recording_id}{METADATA_SUFFIX}"
    if not _find_file_by_name(meta_filename):
        raw_str = json.dumps(metadata_dict) if isinstance(metadata_dict, dict) else str(metadata_json)
        save_file(meta_filename, raw_str.encode("utf-8"), dt=None, dn=None, is_private=1)
        frappe.db.commit()

    call_name = None
    if file_doc:
        call_name = enrich_audio_file(file_doc, {"metadata": normalized, "raw": safe_json_dumps(normalized), "source": "android_sync"})
    else:
        # Create Call Intelligence directly if audio File is pending
        call_name = _sync_call_doc_direct(recording_id, normalized)

    return {
        "ok": True,
        "status": "SUCCESS",
        "recording_id": recording_id,
        "call_intelligence_name": call_name
    }


def _find_file_by_name(filename):
    if not filename:
        return None
    rows = frappe.get_all("File", filters={"file_name": filename}, fields=["name", "file_name", "file_url"], order_by="creation asc", limit=1)
    if not rows:
        base, ext = os.path.splitext(filename)
        if base:
            rows = frappe.get_all("File", filters=[["File", "file_name", "like", f"{base}%"]], fields=["name", "file_name", "file_url"], order_by="creation asc", limit=1)
    if not rows:
        base, ext = os.path.splitext(filename)
        if base:
            rows = frappe.get_all("File", filters=[["File", "file_url", "like", f"%/{base}%"]], fields=["name", "file_name", "file_url"], order_by="creation asc", limit=1)
    return frappe.get_doc("File", rows[0].name) if rows else None


def _find_file_by_recording_id(recording_id):
    if not recording_id:
        return None
    prefix = _recording_prefix(recording_id) or recording_id
    rows = frappe.get_all("File", filters=[["File", "file_name", "like", f"{prefix}%"]], fields=["name", "file_name", "file_url"], order_by="creation asc", limit=50)
    if not rows:
        rows = frappe.get_all("File", filters=[["File", "file_url", "like", f"%/{prefix}%"]], fields=["name", "file_name", "file_url"], order_by="creation asc", limit=50)
    for row in rows:
        fn = (row.file_name or row.file_url or "").lower()
        if any(fn.endswith(ext) for ext in AUDIO_EXTENSIONS):
            return frappe.get_doc("File", row.name)
    return None


def _find_file_by_sha256(sha256):
    if not sha256 or not frappe.db.has_column("File", "content_hash"):
        return None
    rows = frappe.get_all("File", filters={"content_hash": sha256}, fields=["name", "file_name", "file_url"], order_by="creation asc", limit=1)
    return frappe.get_doc("File", rows[0].name) if rows else None


def _sync_call_doc_direct(recording_id, metadata):
    from visa_crm.api.gemini_service import _first_original_call
    existing = _first_original_call({"recording_id": recording_id})
    if existing:
        doc = frappe.get_doc("Call Intelligence", existing)
    else:
        doc = frappe.get_doc({"doctype": "Call Intelligence", "recording_id": recording_id, "processing_status": "Pending"})
        doc.insert(ignore_permissions=True)

    from visa_crm.api.android_metadata import _apply_to_doc
    _apply_to_doc(doc, {"metadata": metadata, "source": "android_sync_direct"})
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return doc.name
