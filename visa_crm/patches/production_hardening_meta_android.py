import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field
from visa_crm.api.meta_utils import has_doctype,has_field

FIELDS={
    "Call Intelligence":(
        ("recording_id","Recording ID","Data",None),("call_uuid","Call UUID","Data",None),("android_metadata_json","Android Metadata JSON","Code","JSON"),("metadata_source","Metadata Source","Data",None),("metadata_status","Metadata Status","Select","Waiting\nValid\nWarning\nMissing\nLegacy"),("metadata_warning","Metadata Warning","Long Text",None),("integrity_status","Integrity Status","Select","Pending\nVerified\nCalculated\nMismatch"),("integrity_failed","Integrity Failed","Check",None),("expected_sha256","Expected SHA256","Data",None),("actual_sha256","Actual SHA256","Data",None),("employee_id","Employee ID","Data",None),("employee_name","Employee Name","Data",None),("employee_email","Employee Email","Data",None),("call_direction","Call Direction","Select","Inbound\nOutbound"),("start_time","Start Time","Datetime",None),("end_time","End Time","Datetime",None),("duration_seconds","Duration Seconds","Int",None),("timezone","Timezone","Data",None),("device_model","Device Model","Data",None),("manufacturer","Manufacturer","Data",None),("android_version","Android Version","Data",None),("device_id","Device ID","Data",None),("sim_slot","SIM Slot","Int",None),("call_source","Call Source","Data",None),("app_version","App Version","Data",None),("audio_format","Audio Format","Data",None),("sha256","SHA256","Data",None),("md5","MD5","Data",None),("mime_type","MIME Type","Data",None),("upload_timestamp","Upload Timestamp","Datetime",None),("upload_retry_count","Upload Retry Count","Int",None),("upload_status","Upload Status","Data",None),("is_auto_uploaded","Auto Uploaded","Check",None),("metadata_file","Metadata File","Link","File"),("audio_file","Audio File","Link","File"),("employee_user","Employee User","Link","User"),("visa_application","Visa Application","Link","Visa Application"),("metadata_next_retry_at","Metadata Next Retry","Datetime",None),("metadata_pair_attempts","Metadata Pair Attempts","Int",None),("gemini_retry_history_json","Gemini Retry History","Long Text",None)
    ),
    "Communication Event":(
        ("meta_campaign_name","Meta Campaign","Data",None),("meta_campaign_id","Meta Campaign ID","Data",None),("meta_adset_name","Meta Ad Set","Data",None),("meta_adset_id","Meta Ad Set ID","Data",None),("meta_ad_name","Meta Ad","Data",None),("meta_ad_id","Meta Ad ID","Data",None),("facebook_page_id","Facebook Page ID","Data",None),("facebook_form_id","Facebook Form ID","Data",None),("facebook_lead_id","Facebook Lead ID","Data",None),("customer360","Customer360","Link","Customer"),("visa_application","Visa Application","Link","Visa Application"),("lead_intake_queue","Lead Intake Queue","Link","Lead Intake Queue"),("original_normalized_payload","Original Normalized Payload","Long Text",None),("meta_attribution_json","Meta Attribution","Long Text",None),("conversation_id","Conversation ID","Data",None),("source_channel","Source Channel","Data",None),("processing_timeline","Processing Timeline","Long Text",None),("employee_phone","Employee Phone","Data",None),("customer_phone","Customer Phone","Data",None),("recording_id","Recording ID","Data",None),("call_source","Call Source","Data",None),("device_id","Device ID","Data",None),("sim_slot","SIM Slot","Int",None),("start_time","Start Time","Datetime",None),("end_time","End Time","Datetime",None)
    ),
    "Visa Application":(
        ("destination","Destination","Data",None),("travel_month","Travel Month","Data",None),("budget","Budget","Data",None),("passport_status","Passport Status","Data",None),("notes","Notes","Long Text",None),("campaign_source","Campaign Source","Data",None),("meta_answers_json","Meta Answers","Long Text",None),("meta_campaign_id","Meta Campaign ID","Data",None),("meta_campaign_name","Meta Campaign Name","Data",None)
    ),
    "CRM Lead":(("custom_ai_lead_score","AI Lead Score","Float",None),),
    "Lead Intake AI Job":(("retry_history_json","Retry History","Long Text",None),),
    "Lead Assignment":(("assignment_decision_json","Assignment Decision","Long Text",None),),
    "Counselor Assignment History":(("assignment_decision_json","Assignment Decision","Long Text",None),),
    "Lost Lead Intelligence":(("call","Call Intelligence","Link","Call Intelligence"),)
}

def execute():
    for doctype,fields in FIELDS.items():
        if not has_doctype(doctype):
            continue
        for fieldname,label,fieldtype,options in fields:
            if has_field(doctype,fieldname):
                continue
            field={"fieldname":fieldname,"label":label,"fieldtype":fieldtype,"insert_after":_insert_after(doctype)}
            if options:
                field["options"]=options
            if doctype=="Call Intelligence" and fieldname in ("recording_id","employee_name","customer_phone","call_direction","duration_seconds","metadata_status","integrity_status","android_version","device_id","sim_slot","metadata_source"):
                field["in_list_view"]=1
            create_custom_field(doctype,field)
        frappe.clear_cache(doctype=doctype)
    _indexes()
    frappe.db.commit()

def _insert_after(doctype):
    meta=frappe.get_meta(doctype)
    for field in ("recording_file","summary","status","lead","communication_event"):
        if meta.has_field(field):
            return field
    return None

def _indexes():
    for doctype,fields,name in (
        ("Pipeline Execution Log",["execution_time","execution_type"],"idx_vc_execution_time"),
        ("Pipeline Execution Log",["queue","stage","execution_time"],"idx_vc_execution_queue"),
        ("Call Intelligence",["metadata_status","metadata_next_retry_at"],"idx_vc_android_pairing")
    ):
        _safe_index(doctype,fields,name)
    _safe_recording_unique()

def _safe_index(doctype,fields,name):
    if not has_doctype(doctype) or not all(has_field(doctype,field) for field in fields) or _index_exists(doctype,name):
        return
    frappe.db.add_index(doctype,fields,index_name=name)

def _safe_recording_unique():
    doctype="Call Intelligence"
    field="recording_id"
    name="uniq_vc_call_recording_id"
    if not has_doctype(doctype) or not has_field(doctype,field) or _unique_field_exists(doctype,field):
        return
    duplicates=frappe.db.sql(f"""select `{field}` from `tab{doctype}` where ifnull(`{field}`,'')!='' group by `{field}` having count(*)>1""",as_list=True)
    for recording_id, in duplicates:
        rows=frappe.get_all(doctype,filters={field:recording_id},fields=["name"],order_by="creation asc")
        canonical=rows[0].name
        for row in rows[1:]:
            values={field:None}
            if has_field(doctype,"duplicate_of"):
                values["duplicate_of"]=canonical
            frappe.db.set_value(doctype,row.name,values,update_modified=False)
    frappe.db.sql(f"""update `tab{doctype}` set `{field}`=null where `{field}`=''""")
    frappe.db.add_unique(doctype,[field],constraint_name=name)

def _index_exists(doctype,name):
    return any(row.Key_name==name for row in frappe.db.sql(f"show index from `tab{doctype}`",as_dict=True))

def _unique_field_exists(doctype,field):
    return any(row.Column_name==field and not row.Non_unique for row in frappe.db.sql(f"show index from `tab{doctype}`",as_dict=True))

def verify():
    return {
        "pipeline_execution_log":has_doctype("Pipeline Execution Log"),
        "production_diagnostics_report":bool(frappe.db.exists("Report","Production Diagnostics")),
        "recording_id_unique":_unique_field_exists("Call Intelligence","recording_id"),
        "recording_indexes":[{"name":row.Key_name,"column":row.Column_name,"unique":not bool(row.Non_unique)} for row in frappe.db.sql("show index from `tabCall Intelligence`",as_dict=True) if row.Column_name=="recording_id"],
        "execution_queue_index":_index_exists("Pipeline Execution Log","idx_vc_execution_queue"),
        "android_fields":all(has_field("Call Intelligence",field) for field in ("recording_id","android_metadata_json","metadata_status","integrity_status","employee_id","customer_phone","device_id","app_version")),
        "communication_fields":all(has_field("Communication Event",field) for field in ("meta_campaign_id","facebook_lead_id","visa_application","lead_intake_queue","original_normalized_payload")),
        "visa_fields":all(has_field("Visa Application",field) for field in ("destination","travel_month","budget","passport_status","meta_answers_json")),
        "ai_lead_score":has_field("CRM Lead","custom_ai_lead_score")
    }
