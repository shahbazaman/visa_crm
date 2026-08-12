import hashlib
import json
import os
import re
import frappe
from frappe.utils import add_to_date,cint,get_datetime,now_datetime
from frappe.utils.file_manager import get_file_path
from visa_crm.api.meta_utils import has_field,safe_json_dumps

AUDIO_EXTENSIONS=(".m4a",".mp3",".wav",".aac",".mpeg",".ogg",".webm",".mp4")
METADATA_SUFFIX="_metadata.json"
RECORDING_PREFIX=re.compile(r"^(CALL-\d{8}-[A-Za-z0-9]+-[A-Za-z0-9]+)",re.I)
VALID_DIRECTIONS={"INCOMING":"Inbound","OUTGOING":"Outbound","INBOUND":"Inbound","OUTBOUND":"Outbound"}
AUTHORITATIVE_FIELDS=("recording_id","call_uuid","employee_id","employee_name","employee_phone","employee_email","customer_phone","call_direction","start_time","end_time","duration_seconds","timezone","device_model","manufacturer","android_version","device_id","sim_slot","call_source","app_version","audio_format","sha256","md5","file_size","mime_type","upload_timestamp","upload_retry_count","upload_status","is_auto_uploaded")

def load_metadata(source):
    if isinstance(source,dict):
        raw=safe_json_dumps(source)
        return {"metadata":_normalize(dict(source)),"raw":raw,"source":"object"}
    if getattr(source,"doctype",None)=="Call Intelligence":
        raw=source.get("android_metadata_json")
        return _parse_raw(raw,"stored")
    file_doc=_file_doc(source)
    if not file_doc:
        return {"metadata":{},"raw":None,"source":None}
    filename=(file_doc.file_name or os.path.basename(file_doc.file_url or "")).lower()
    if filename.endswith(METADATA_SUFFIX):
        try:
            path=get_file_path(file_doc.file_url)
            with open(path,"r",encoding="utf-8") as handle:
                return _parse_raw(handle.read(),"metadata_file",file_doc.name)
        except Exception as exc:
            return {"metadata":{},"raw":None,"source":"metadata_file","file":file_doc.name,"warnings":[f"Metadata file could not be read: {exc}"]}
    description=file_doc.get("description") if file_doc.meta.has_field("description") else None
    return _parse_raw(description,"description",file_doc.name)

def validate_metadata(metadata):
    data=_normalize(dict(metadata or {}))
    warnings=[]
    for field in ("recording_id","employee_id","employee_name","customer_phone","app_version"):
        if not data.get(field):
            warnings.append(f"{field} is missing")
    if data.get("call_direction") not in ("Inbound","Outbound"):
        warnings.append("call_direction must be INCOMING or OUTGOING")
    if cint(data.get("duration_seconds"))<=0:
        warnings.append("duration_seconds must be positive")
    for field in ("start_time","end_time","upload_timestamp"):
        if data.get(field):
            try:
                get_datetime(data[field])
            except Exception:
                warnings.append(f"{field} is not valid ISO8601")
    digest=data.get("sha256")
    if digest and not re.fullmatch(r"[a-fA-F0-9]{64}",str(digest).replace("sha256:","")):
        warnings.append("sha256 is invalid")
    return warnings

def extract_metadata(source):
    if getattr(source,"doctype",None)=="Call Intelligence":
        stored=load_metadata(source)
        if stored.get("metadata"):
            stored["warnings"]=validate_metadata(stored["metadata"])
            return stored
        file_doc=_file_doc_by_url(source.get("recording_file"))
    else:
        file_doc=_file_doc(source)
    if not file_doc:
        return {"metadata":{},"raw":None,"source":None,"warnings":["Audio File record was not found"]}
    companion=_metadata_file_for(file_doc)
    if companion:
        result=load_metadata(companion)
    else:
        result=load_metadata(file_doc)
    if not result.get("metadata"):
        result=_filename_fallback(file_doc)
    result["warnings"]=list(result.get("warnings") or [])+validate_metadata(result.get("metadata"))
    result["audio_file"]=file_doc.name
    if companion:
        result["metadata_file"]=companion.name
    return result

def pair_audio_with_metadata(source):
    file_doc=_file_doc(source)
    if not file_doc:
        return []
    filename=file_doc.file_name or os.path.basename(file_doc.file_url or "")
    if filename.lower().endswith(METADATA_SUFFIX):
        result=load_metadata(file_doc)
        prefix=_recording_prefix(filename) or result.get("metadata",{}).get("recording_id")
        files=_audio_files_for_prefix(prefix)
        return [enrich_audio_file(row,result) for row in files]
    return [enrich_audio_file(file_doc,extract_metadata(file_doc))]

def extract_metadata_from_description(description):
    return _parse_raw(description,"description")

def calculate_hash_if_missing(file_source,metadata=None):
    metadata=metadata or {}
    expected=str(metadata.get("sha256") or metadata.get("file_hash") or "").replace("sha256:","")
    file_doc=_file_doc(file_source)
    file_url=file_doc.file_url if file_doc else str(file_source or "")
    actual=None
    try:
        path=get_file_path(file_url)
        digest=hashlib.sha256()
        with open(path,"rb") as handle:
            for chunk in iter(lambda:handle.read(1024*1024),b""):
                digest.update(chunk)
        actual=digest.hexdigest()
    except Exception:
        pass
    return {"expected":expected or actual,"actual":actual,"matches":None if not expected or not actual else expected.lower()==actual.lower()}

def prepare_call_doc(call_doc,file_doc):
    result=extract_metadata(file_doc)
    _apply_to_doc(call_doc,result,file_doc)
    return result

def enrich_audio_file(file_source,metadata_result=None):
    from visa_crm.api import gemini_service
    file_doc=_file_doc(file_source)
    if not file_doc:
        return None
    call_name=gemini_service._existing_audio_call(file_doc)
    if not call_name:
        call_name=gemini_service._create_call_for_file_once(file_doc)
    if not call_name:
        return None
    doc=frappe.get_doc("Call Intelligence",call_name)
    result=metadata_result or extract_metadata(file_doc)
    _apply_to_doc(doc,result,file_doc)
    values={field:doc.get(field) for field in _call_fields(doc) if doc.get(field) is not None}
    if values:
        frappe.db.set_value("Call Intelligence",doc.name,values,update_modified=False)
    _link_call(doc.name)
    frappe.db.commit()
    doc.reload()
    if not should_wait_for_metadata(doc):
        try:
            gemini_service.enqueue_processing(doc)
        except Exception:
            frappe.logger("visa_crm.android").warning(safe_json_dumps({"event":"call_ai_enqueue_failed","call":doc.name,"traceback":frappe.get_traceback()}))
    return doc.name

def handle_file_upload(doc,method=None):
    filename=doc.file_name or os.path.basename(doc.file_url or "")
    low=filename.lower()
    if low.endswith(METADATA_SUFFIX):
        pair_audio_with_metadata(doc)
    elif low.endswith(AUDIO_EXTENSIONS):
        pair_audio_with_metadata(doc)

def process_pending_metadata_pairs(limit=100):
    if not frappe.db.exists("DocType","Call Intelligence") or not has_field("Call Intelligence","metadata_status"):
        return 0
    now=now_datetime()
    rows=frappe.get_all("Call Intelligence",filters={"metadata_status":["in",["Waiting","Missing"]]} ,fields=["name","recording_file","creation","metadata_next_retry_at"],order_by="creation asc",limit=limit)
    processed=0
    for row in rows:
        if row.metadata_next_retry_at and get_datetime(row.metadata_next_retry_at)>now:
            continue
        file_doc=_file_doc_by_url(row.recording_file)
        result=extract_metadata(file_doc) if file_doc else {"metadata":{},"warnings":["Audio File record was not found"]}
        if result.get("metadata") and result.get("source")!="filename":
            enrich_audio_file(file_doc,result)
            processed+=1
            continue
        age=(now-get_datetime(row.creation)).total_seconds()
        attempts=cint(frappe.db.get_value("Call Intelligence",row.name,"metadata_pair_attempts"))+1
        values={"metadata_pair_attempts":attempts,"metadata_next_retry_at":add_to_date(now,minutes=1)}
        if age>=300:
            values.update({"metadata_status":"Missing","metadata_source":"Fallback","metadata_warning":"Companion Android metadata was not received; legacy fallback remains active","metadata_next_retry_at":add_to_date(now,hours=1)})
        frappe.db.set_value("Call Intelligence",row.name,values,update_modified=False)
    if rows:
        frappe.db.commit()
    return processed

def should_wait_for_metadata(doc):
    return bool(_is_modern_audio(doc.get("audio_filename") or doc.get("recording_file")) and doc.get("metadata_status")=="Waiting")

def _apply_to_doc(doc,result,file_doc=None):
    data=_normalize(dict(result.get("metadata") or {}))
    warnings=list(dict.fromkeys(result.get("warnings") or validate_metadata(data)))
    raw=result.get("raw")
    if not data:
        if _is_modern_audio((file_doc.file_name if file_doc else None) or doc.get("recording_file")):
            _set(doc,"metadata_status","Waiting")
            _set(doc,"metadata_source","Pending")
            _set(doc,"metadata_next_retry_at",add_to_date(now_datetime(),minutes=1))
        else:
            _set(doc,"metadata_status","Legacy")
            _set(doc,"metadata_source","Filename")
        return
    if raw and not doc.get("android_metadata_json"):
        _set(doc,"android_metadata_json",raw)
    _set(doc,"metadata_source",result.get("source"))
    _set(doc,"metadata_status","Warning" if warnings else "Valid")
    _set(doc,"metadata_warning","\n".join(warnings) if warnings else "")
    for field in AUTHORITATIVE_FIELDS:
        value=data.get(field)
        if value is not None:
            _set(doc,field,value)
    _set(doc,"customer_phone_extracted",data.get("customer_phone"))
    _set(doc,"employee_phone_extracted",data.get("employee_phone"))
    _set(doc,"call_duration_seconds",data.get("duration_seconds"))
    if file_doc:
        _set(doc,"audio_file",file_doc.name)
    if result.get("metadata_file"):
        _set(doc,"metadata_file",result["metadata_file"])
    integrity=calculate_hash_if_missing(file_doc or doc.get("recording_file"),data)
    _set(doc,"expected_sha256",integrity["expected"])
    _set(doc,"actual_sha256",integrity["actual"])
    if integrity["matches"] is False:
        _set(doc,"integrity_status","Mismatch")
        _set(doc,"integrity_failed",1)
        warning="Uploaded audio SHA256 does not match Android metadata"
        _set(doc,"metadata_warning","\n".join(filter(None,[doc.get("metadata_warning"),warning])))
    elif integrity["actual"]:
        _set(doc,"integrity_status","Verified" if integrity["matches"] else "Calculated")
    employee,user=_employee(data)
    _set(doc,"employee_match",employee)
    _set(doc,"employee_user",user)

def _link_call(call_name):
    from visa_crm.api.customer360 import match_lead_data
    doc=frappe.get_doc("Call Intelligence",call_name)
    phone=doc.get("customer_phone") or doc.get("customer_phone_extracted")
    matches=match_lead_data({"phone":phone}) if phone else {}
    values={}
    if matches.get("customer") and not doc.get("customer_360_match"):
        values["customer_360_match"]=matches["customer"]
    if matches.get("lead") and not doc.get("lead_match"):
        values["lead_match"]=matches["lead"]
    lead=values.get("lead_match") or doc.get("lead_match")
    customer=values.get("customer_360_match") or doc.get("customer_360_match")
    visa=None
    if frappe.db.exists("DocType","Visa Application"):
        if lead and frappe.get_meta("Visa Application").has_field("lead"):
            visa=frappe.db.get_value("Visa Application",{"lead":lead},"name")
        if not visa and customer and frappe.get_meta("Visa Application").has_field("customer"):
            visa=frappe.db.get_value("Visa Application",{"customer":customer},"name")
    if visa:
        values["visa_application"]=visa
    if values:
        frappe.db.set_value("Call Intelligence",call_name,{field:value for field,value in values.items() if has_field("Call Intelligence",field)},update_modified=False)
    event=doc.get("communication_event")
    if event and frappe.db.exists("Communication Event",event):
        enrich_communication_event(event,frappe.get_doc("Call Intelligence",call_name))

def enrich_communication_event(event_name,call_doc):
    values={"direction":call_doc.get("call_direction") or "Inbound","employee":call_doc.get("employee_match"),"customer":call_doc.get("customer_360_match"),"lead":call_doc.get("lead_match"),"visa_application":call_doc.get("visa_application"),"employee_phone":call_doc.get("employee_phone") or call_doc.get("employee_phone_extracted"),"customer_phone":call_doc.get("customer_phone") or call_doc.get("customer_phone_extracted"),"phone":call_doc.get("customer_phone") or call_doc.get("customer_phone_extracted"),"duration":call_doc.get("duration_seconds") or call_doc.get("call_duration_seconds"),"recording_id":call_doc.get("recording_id"),"call_source":call_doc.get("call_source"),"device_id":call_doc.get("device_id"),"sim_slot":call_doc.get("sim_slot"),"start_time":call_doc.get("start_time"),"end_time":call_doc.get("end_time")}
    values={field:value for field,value in values.items() if value is not None and has_field("Communication Event",field)}
    if values:
        frappe.db.set_value("Communication Event",event_name,values,update_modified=False)

def _parse_raw(raw,source,file_name=None):
    if not raw:
        return {"metadata":{},"raw":raw,"source":source,"file":file_name}
    try:
        data=json.loads(raw) if isinstance(raw,str) else dict(raw)
        if not isinstance(data,dict):
            raise ValueError("metadata JSON must be an object")
        return {"metadata":_normalize(data),"raw":raw if isinstance(raw,str) else safe_json_dumps(raw),"source":source,"file":file_name}
    except Exception as exc:
        return {"metadata":{},"raw":raw,"source":source,"file":file_name,"warnings":[f"Invalid metadata JSON: {exc}"]}

def _normalize(data):
    if not data:
        return {}
    if data.get("file_hash") and not data.get("sha256"):
        data["sha256"]=str(data["file_hash"]).replace("sha256:","")
    direction=str(data.get("call_direction") or data.get("direction") or "").upper()
    if direction in VALID_DIRECTIONS:
        data["call_direction"]=VALID_DIRECTIONS[direction]
    if data.get("duration") and not data.get("duration_seconds"):
        data["duration_seconds"]=data["duration"]
    return data

def _filename_fallback(file_doc):
    filename=file_doc.file_name or os.path.basename(file_doc.file_url or "")
    prefix=_recording_prefix(filename)
    return {"metadata":{"recording_id":prefix} if prefix else {},"raw":None,"source":"filename","file":file_doc.name}

def _metadata_file_for(audio_file):
    prefix=_recording_prefix(audio_file.file_name or os.path.basename(audio_file.file_url or ""))
    if not prefix:
        return None
    rows=frappe.get_all("File",filters={"file_name":["like",f"{prefix}%{METADATA_SUFFIX}"]},fields=_file_fields(),order_by="creation desc",limit=1)
    return frappe.get_doc("File",rows[0].name) if rows else None

def _audio_files_for_prefix(prefix):
    if not prefix:
        return []
    rows=frappe.get_all("File",filters={"file_name":["like",f"{prefix}%"]},fields=_file_fields(),order_by="creation asc",limit=50)
    return [frappe.get_doc("File",row.name) for row in rows if (row.file_name or "").lower().endswith(AUDIO_EXTENSIONS)]

def _recording_prefix(filename):
    match=RECORDING_PREFIX.match(os.path.basename(filename or ""))
    return match.group(1) if match else None

def _is_modern_audio(filename):
    return bool(_recording_prefix(filename))

def _employee(data):
    if not frappe.db.exists("DocType","Employee"):
        return None,None
    employee=None
    employee_id=data.get("employee_id")
    if employee_id and frappe.db.exists("Employee",employee_id):
        employee=employee_id
    if not employee:
        for field,value in (("employee_number",employee_id),("employee_name",data.get("employee_name")),("user_id",data.get("employee_email")),("company_email",data.get("employee_email"))):
            if value and frappe.get_meta("Employee").has_field(field):
                employee=frappe.db.get_value("Employee",{field:value},"name")
                if employee:
                    break
    return employee,frappe.db.get_value("Employee",employee,"user_id") if employee and frappe.get_meta("Employee").has_field("user_id") else None

def _file_doc(source):
    if not source:
        return None
    if getattr(source,"doctype",None)=="File":
        return source
    if getattr(source,"file_url",None) and getattr(source,"file_name",None):
        name=getattr(source,"name",None)
        return frappe.get_doc("File",name) if name and frappe.db.exists("File",name) else source
    if isinstance(source,str) and frappe.db.exists("File",source):
        return frappe.get_doc("File",source)
    if isinstance(source,str):
        return _file_doc_by_url(source)
    return None

def _file_doc_by_url(file_url):
    name=frappe.db.get_value("File",{"file_url":file_url},"name") if file_url else None
    return frappe.get_doc("File",name) if name else None

def _file_fields():
    fields=["name","file_name","file_url","creation"]
    if frappe.get_meta("File").has_field("description"):
        fields.append("description")
    return fields

def _set(doc,field,value):
    if value is not None and doc.meta.has_field(field):
        doc.set(field,value)

def _call_fields(doc):
    return tuple(field.fieldname for field in doc.meta.fields if field.fieldname in set(AUTHORITATIVE_FIELDS)|{"android_metadata_json","metadata_source","metadata_status","metadata_warning","integrity_status","integrity_failed","expected_sha256","actual_sha256","metadata_file","audio_file","employee_user","employee_match","customer_phone_extracted","employee_phone_extracted","call_duration_seconds","visa_application","metadata_next_retry_at","metadata_pair_attempts"})
