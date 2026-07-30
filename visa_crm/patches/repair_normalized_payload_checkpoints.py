import frappe
from visa_crm.api.meta_utils import safe_json_dumps

def execute():
    if not frappe.db.exists("DocType","Lead Intake Queue") or not frappe.db.exists("DocType","Lead Intake Stage"):
        return
    from visa_crm.api.pipeline_engine import repair_normalization_checkpoint
    repaired=0
    for queue_name in frappe.get_all("Lead Intake Queue",pluck="name",limit_page_length=0):
        repaired+=int(repair_normalization_checkpoint(queue_name))
    frappe.db.commit()
    frappe.logger("visa_crm.migration").info(safe_json_dumps({"event":"normalized_payload_checkpoint_repair","repaired":repaired}))
