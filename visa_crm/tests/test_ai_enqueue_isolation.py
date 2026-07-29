import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock,patch
from visa_crm.api import communication_center,intake_processor

class CallbackManager:
    def __init__(self):
        self.callbacks=[]
    def add(self,callback):
        self.callbacks.append(callback)
    def run(self):
        while self.callbacks:
            self.callbacks.pop(0)()

class QueueDoc:
    def __init__(self):
        self.name="LIQ-TEST-AI"
        self.source_lead_id="META-TEST-AI"
        self.status="Lead Received"
        self.raw_payload="{}"

class TestAIEnqueueIsolation(unittest.TestCase):
    def test_redis_offline_does_not_fail_mandatory_pipeline(self):
        queue=QueueDoc()
        callbacks=CallbackManager()
        rollback=Mock()
        finished={}
        states=[]
        create_or_link=Mock(return_value={"lead":"CRM-LEAD-TEST","customer":"CUSTOMER-TEST"})
        create_followup=Mock(return_value="TODO-TEST")
        real_get_doc=intake_processor.frappe.get_doc
        def commit():
            callbacks.run()
        def get_doc(doctype,*args,**kwargs):
            return queue if doctype=="Lead Intake Queue" else real_get_doc(doctype,*args,**kwargs)
        def update_queue(doc,data,payload,status):
            doc.status=status
        def link_matches(doc,matches):
            doc.status="Lead Created"
        def finish(doc,lead,customer,employee,event,todo,visa):
            doc.status="Processed"
            finished.update({"lead":lead,"customer":customer,"visa":visa,"event":event,"todo":todo,"employee":employee})
        def communication_event(data,lead,customer,employee,visa,queue_name,context):
            event=SimpleNamespace(name="COM-TEST-AI",channel_id=queue_name)
            communication_center.after_communication_insert(event)
            return event.name
        data={"source_lead_id":queue.source_lead_id,"customer_name":"Queue Test","phone":"+971501234567","meta_fields":{}}
        patches=(
            patch.object(intake_processor,"_claim",return_value=True),
            patch.object(intake_processor.frappe,"get_doc",side_effect=get_doc),
            patch.object(intake_processor.frappe.db,"commit",side_effect=commit),
            patch.object(intake_processor.frappe.db,"rollback",rollback),
            patch.object(intake_processor,"get_meta_settings",return_value=SimpleNamespace()),
            patch.object(intake_processor,"fetch_lead",return_value={"id":queue.source_lead_id,"field_data":[]}),
            patch.object(intake_processor,"normalize_lead",return_value=data),
            patch.object(intake_processor,"_update_queue",side_effect=update_queue),
            patch.object(intake_processor,"link_or_create_lead",create_or_link),
            patch.object(intake_processor,"_link_matches",side_effect=link_matches),
            patch.object(intake_processor,"create_for_lead",return_value="VISA-TEST"),
            patch.object(intake_processor,"mark_lead_stage"),
            patch.object(intake_processor,"qualify_lead"),
            patch.object(intake_processor,"create_deal_if_supported"),
            patch.object(intake_processor,"assign_lead",return_value="EMP-TEST"),
            patch.object(intake_processor,"_communication_event",side_effect=communication_event),
            patch.object(intake_processor,"create_meta_followup",create_followup),
            patch.object(intake_processor,"_finish",side_effect=finish),
            patch.object(intake_processor,"_pipeline_stage"),
            patch.object(intake_processor,"meta_debug_log"),
            patch.object(intake_processor,"log_info"),
            patch.object(intake_processor,"log_exception"),
            patch.object(communication_center,"attach_context"),
            patch.object(communication_center,"_queue_name",return_value=queue.name),
            patch.object(communication_center,"_persist_ai_state",side_effect=lambda name,status,**kwargs:states.append((name,status,kwargs))),
            patch.object(communication_center.frappe.db,"after_commit",callbacks),
            patch.object(communication_center.frappe,"enqueue",side_effect=ConnectionRefusedError("Redis offline"))
        )
        with ExitStack() as stack:
            for context in patches:
                stack.enter_context(context)
            intake_processor.process_queue(queue.name)
        self.assertEqual(queue.status,"Processed")
        self.assertEqual(finished,{"lead":"CRM-LEAD-TEST","customer":"CUSTOMER-TEST","visa":"VISA-TEST","event":"COM-TEST-AI","todo":"TODO-TEST","employee":"EMP-TEST"})
        self.assertIn((queue.name,"Pending",{}),states)
        failure=next(kwargs for name,status,kwargs in states if name==queue.name and status=="Failed")
        self.assertTrue(failure.get("increment_retry"))
        self.assertIn("Redis offline",failure.get("ai_error"))
        self.assertIn("ConnectionRefusedError",failure.get("ai_traceback"))
        create_or_link.assert_called_once()
        create_followup.assert_called_once()
        rollback.assert_not_called()
