from unittest.mock import patch
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime,time_diff_in_seconds
from visa_crm.api import pipeline_stage_services
from visa_crm.api.execution_history import record

class TestProductionHardening(FrappeTestCase):
    def test_ai_retry_schedule(self):
        expected=(30,120,300,600,1800,3600,3600)
        for attempt,seconds in enumerate(expected,1):
            now=now_datetime()
            retry=pipeline_stage_services.ai_retry_at(attempt,now)
            self.assertAlmostEqual(time_diff_in_seconds(retry,now),seconds,delta=1)

    def test_execution_history_is_durable(self):
        if not frappe.db.exists("DocType","Pipeline Execution Log"):
            self.skipTest("Pipeline Execution Log is not migrated")
        name=record(stage="TEST",execution_type="Stage",result="SUCCESS",details={"test":True})
        self.assertTrue(frappe.db.exists("Pipeline Execution Log",name))
        frappe.db.delete("Pipeline Execution Log",{"name":name})

    def test_ai_todo_description_is_never_empty(self):
        doc=frappe._dict({"name":"CE-TEST","lead":None,"customer":None,"assigned_user":None})
        with patch("visa_crm.api.ai_intelligence.has_doctype",return_value=True),patch("visa_crm.api.ai_intelligence.has_field",return_value=False),patch("visa_crm.api.ai_intelligence.frappe.db.exists",return_value=False),patch("visa_crm.api.ai_intelligence.frappe.new_doc") as new_doc:
            todo=frappe._dict()
            todo.meta=frappe._dict({"fields":[]})
            todo.insert=lambda **kwargs:None
            new_doc.return_value=todo
            from visa_crm.api.ai_intelligence import _auto_task
            _auto_task(doc,{"auto_task":"  "})
            self.assertTrue(todo.description)
