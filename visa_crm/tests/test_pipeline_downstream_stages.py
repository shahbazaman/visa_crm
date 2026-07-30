from unittest.mock import patch
import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api.pipeline_engine import ensure_stage_ledger
from visa_crm.api.pipeline_stage_services import communication_event,crm_lead,customer360,follow_up,visa_application

class TestPipelineDownstreamStages(FrappeTestCase):
    def setUp(self):
        suffix=frappe.generate_hash(length=10)
        self.source=f"DOWN-{suffix}"
        phone=f"+9715{''.join(str(ord(char)%10) for char in suffix)[:8]}"
        data={"source_lead_id":self.source,"customer_name":f"Downstream {suffix}","phone":phone,"email":f"{suffix}@example.com","visa_type":"Tourist","country_interested":"UAE","meta_fields":{"full_name":f"Downstream {suffix}","phone":phone},"meta_raw_fields":"{}"}
        doc=frappe.new_doc("Lead Intake Queue")
        doc.source_lead_id=self.source
        doc.status="Lead Downloaded"
        doc.raw_payload="{}"
        doc.normalized_payload=frappe.as_json(data)
        doc.normalized_payload_hash=frappe.generate_hash(length=32)
        doc.insert(ignore_permissions=True)
        self.queue=doc.name
        ensure_stage_ledger(self.queue)
        customer360(self.queue)
        crm_lead(self.queue)
        frappe.db.commit()

    def tearDown(self):
        queue=frappe.get_doc("Lead Intake Queue",self.queue)
        for doctype,filters in (("Activity Timeline",{"meta_intake_key":f"activity:{self.queue}"}),("Reminder Scheduler",{"meta_intake_key":f"reminder:{self.queue}"}),("ToDo",{"meta_intake_key":f"followup:{self.queue}"}),("Communication Event",{"event_id":f"meta:{self.source}"}),("Visa Application",{"meta_intake_key":f"visa:{self.queue}"}),("Customer Identity",{"customer":queue.matched_customer}),("CRM Lead",{"name":queue.matched_lead}),("Customer",{"name":queue.matched_customer}),("Lead Intake Stage",{"queue":self.queue}),("Lead Intake Queue",{"name":self.queue})):
            if frappe.db.exists("DocType",doctype):
                frappe.db.delete(doctype,filters)
        frappe.db.commit()

    def test_downstream_outputs_are_idempotent(self):
        with patch("visa_crm.api.communication_center.frappe.enqueue"):
            visa1=visa_application(self.queue)["visa_application"]
            visa2=visa_application(self.queue)["visa_application"]
            event1=communication_event(self.queue)["communication_event"]
            event2=communication_event(self.queue)["communication_event"]
            todo1=follow_up(self.queue)["followup"]
            todo2=follow_up(self.queue)["followup"]
        self.assertEqual(visa1,visa2)
        self.assertEqual(event1,event2)
        self.assertEqual(todo1,todo2)
        self.assertEqual(frappe.db.count("Visa Application",{"meta_intake_key":f"visa:{self.queue}"}),1)
        self.assertEqual(frappe.db.count("Communication Event",{"event_id":f"meta:{self.source}"}),1)
        self.assertEqual(frappe.db.count("ToDo",{"meta_intake_key":f"followup:{self.queue}"}),1)
        if frappe.db.exists("DocType","Reminder Scheduler") and frappe.get_meta("Reminder Scheduler").has_field("meta_intake_key"):
            self.assertEqual(frappe.db.count("Reminder Scheduler",{"meta_intake_key":f"reminder:{self.queue}"}),1)
        if frappe.db.exists("DocType","Activity Timeline") and frappe.get_meta("Activity Timeline").has_field("meta_intake_key"):
            self.assertEqual(frappe.db.count("Activity Timeline",{"meta_intake_key":f"activity:{self.queue}"}),1)
