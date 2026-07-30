from unittest.mock import patch
import frappe
from frappe.tests.utils import FrappeTestCase
from visa_crm.api import intake_processor

class TestSchedulerOrchestration(FrappeTestCase):
    def test_one_queue_exception_does_not_block_later_queues(self):
        rows=[frappe._dict({"name":"QUEUE-FAIL"}),frappe._dict({"name":"QUEUE-NEXT"})]
        with patch("visa_crm.api.intake_processor.recover_expired_leases"),patch("visa_crm.api.intake_processor.services.recover_stale_ai_jobs"),patch("visa_crm.api.intake_processor._recover_stale_fetches"),patch("visa_crm.api.intake_processor._pending_rows",return_value=rows),patch("visa_crm.api.intake_processor.process_queue",side_effect=[RuntimeError("unexpected orchestration failure"),{"ok":True}]) as process:
            count=intake_processor.process_pending()
        self.assertEqual(count,2)
        self.assertEqual([call.args[0] for call in process.call_args_list],["QUEUE-FAIL","QUEUE-NEXT"])
