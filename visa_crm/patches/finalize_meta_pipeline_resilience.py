import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from visa_crm.api.meta_utils import has_doctype,has_field,safe_json_dumps

ATTRIBUTION_FIELDS=("facebook_lead_id","facebook_form_id","facebook_page_id","meta_campaign_id","meta_campaign_name","meta_adset_id","meta_adset_name","meta_ad_id","meta_ad_name")
QUEUE_AUDIT_FIELDS=("source_lead_id","event_type","page_id","form_id","meta_webhook_event","raw_payload","graph_payload","graph_api_request","graph_api_response","custom_answers","normalized_payload")
REQUIRED_INDEXES={
    "Lead Intake Queue":("uniq_meta_source_lead_id","idx_vc_queue_orchestration"),
    "Lead Intake Stage":("stage_key","idx_vc_stage_due","idx_vc_stage_lease","idx_vc_stage_queue"),
    "Customer Identity":("identity_hash","idx_vc_identity_customer"),
    "CRM Lead":("uniq_vc_facebook_lead",),
    "Communication Event":("uniq_vc_communication_event","idx_vc_comm_queue"),
    "Lead Intake AI Job":("idempotency_key","idx_vc_ai_job_due","idx_vc_ai_job_queue")
}
UNIQUE_ALTERNATES={"uniq_meta_source_lead_id":"source_lead_id","uniq_vc_facebook_lead":"facebook_lead_id","uniq_vc_communication_event":"event_id","stage_key":"stage_key","identity_hash":"identity_hash","idempotency_key":"idempotency_key"}

def execute():
    from visa_crm.patches import complete_meta_pipeline_resilience_schema as complete
    from visa_crm.patches import create_meta_stage_orchestration as stage
    stage._custom_fields()
    stage._queue_status_options()
    stage._indexes()
    complete._fields()
    complete._indexes()
    stage._backfill_attribution()
    stage._backfill_stages()
    complete._backfill_communication_links()
    complete._backfill_assignment_links()
    complete._backfill_ai_jobs()
    _read_only_fields()
    _canonical_rollups()
    _verification_log()
    frappe.clear_cache()
    frappe.db.commit()

def repair_constraints():
    from visa_crm.patches import complete_meta_pipeline_resilience_schema as complete
    from visa_crm.patches import create_meta_stage_orchestration as stage
    stage._indexes()
    complete._indexes()
    frappe.db.commit()
    return verification()

def _read_only_fields():
    for field in ATTRIBUTION_FIELDS:
        _read_only("CRM Lead",field)
    for field in QUEUE_AUDIT_FIELDS:
        _read_only("Lead Intake Queue",field)

def _read_only(doctype,fieldname):
    if not has_doctype(doctype) or not has_field(doctype,fieldname):
        return
    filters={"doc_type":doctype,"field_name":fieldname,"property":"read_only"}
    name=frappe.db.get_value("Property Setter",filters,"name")
    if name:
        if str(frappe.db.get_value("Property Setter",name,"value"))!="1":
            frappe.db.set_value("Property Setter",name,"value","1",update_modified=False)
        return
    make_property_setter(doctype,fieldname,"read_only",1,"Check",validate_fields_for_doctype=False)

def _canonical_rollups():
    if not has_doctype("Lead Intake Queue") or not has_doctype("Lead Intake Stage"):
        return
    from visa_crm.api.pipeline_engine import rollup_queue
    for queue_name in frappe.get_all("Lead Intake Queue",pluck="name",limit_page_length=0):
        if frappe.db.exists("Lead Intake Stage",{"queue":queue_name}):
            rollup_queue(queue_name)

def _verification_log():
    result=verification()
    level="warning" if not result["ok"] else "info"
    getattr(frappe.logger("visa_crm.migration"),level)(safe_json_dumps({"event":"meta_resilience_schema_verification",**result}))

def verification():
    result={}
    for doctype,required in REQUIRED_INDEXES.items():
        if not has_doctype(doctype):
            result[doctype]={"exists":False,"missing":list(required)}
            continue
        indexes=frappe.db.sql(f"show index from `tab{doctype}`",as_dict=True)
        names={row.Key_name for row in indexes}
        columns={row.Column_name for row in indexes if not row.Non_unique}
        missing=[name for name in required if name not in names and UNIQUE_ALTERNATES.get(name) not in columns]
        result[doctype]={"exists":True,"missing":missing}
    read_only={f"CRM Lead.{field}":bool(frappe.db.get_value("Property Setter",{"doc_type":"CRM Lead","field_name":field,"property":"read_only","value":"1"},"name")) for field in ATTRIBUTION_FIELDS}
    read_only.update({f"Lead Intake Queue.{field}":bool(frappe.db.get_value("Property Setter",{"doc_type":"Lead Intake Queue","field_name":field,"property":"read_only","value":"1"},"name")) for field in QUEUE_AUDIT_FIELDS if has_field("Lead Intake Queue",field)})
    duplicates={}
    for doctype,field in (("Lead Intake Queue","source_lead_id"),("CRM Lead","facebook_lead_id"),("Communication Event","event_id"),("Lead Intake Stage","stage_key"),("Customer Identity","identity_hash"),("Lead Intake AI Job","idempotency_key")):
        rows=frappe.db.sql(f"""select count(*) total from (select `{field}` from `tab{doctype}` where ifnull(`{field}`,'')!='' group by `{field}` having count(*)>1) duplicates""",as_dict=True) if has_doctype(doctype) and has_field(doctype,field) else []
        duplicates[f"{doctype}.{field}"]=rows[0].total if rows else None
    ok=not any(row["missing"] for row in result.values()) and all(read_only.values()) and not any(value for value in duplicates.values() if value is not None)
    return {"ok":ok,"indexes":result,"read_only":read_only,"duplicate_groups":duplicates}
