import os
import socket
import time
import frappe
from frappe.utils import cint,now_datetime
from visa_crm.api.meta_utils import safe_json_dumps

DOCTYPE="Pipeline Execution Log"

def worker_id():
    return f"{frappe.local.site or 'site'}:{socket.gethostname()}:{os.getpid()}"

def record(queue=None,stage=None,execution_type="Stage",result="SUCCESS",started_at=None,duration_ms=None,retry_count=0,warning_count=0,failure_reason=None,next_retry=None,traceback=None,details=None,worker=None):
    if not frappe.db.exists("DocType",DOCTYPE):
        return None
    try:
        now=now_datetime()
        if duration_ms is None and started_at:
            duration_ms=max(int((now-started_at).total_seconds()*1000),0)
        doc=frappe.new_doc(DOCTYPE)
        doc.update({"queue":queue if queue and frappe.db.exists("Lead Intake Queue",queue) else None,"stage":stage,"execution_type":execution_type,"execution_time":now,"duration_ms":cint(duration_ms),"worker_id":worker or worker_id(),"result":result,"retry_count":cint(retry_count),"warning_count":cint(warning_count),"failure_reason":failure_reason,"next_retry_at":next_retry,"traceback":traceback,"details_json":safe_json_dumps(details) if details is not None else None})
        doc.insert(ignore_permissions=True)
        return doc.name
    except Exception:
        frappe.logger("visa_crm.execution").error(safe_json_dumps({"event":"execution_history_write_failed","queue":queue,"stage":stage,"traceback":frappe.get_traceback()}))
        return None

class ExecutionTimer:
    def __init__(self,queue=None,stage=None,execution_type="Scheduler",details=None):
        self.queue=queue
        self.stage=stage
        self.execution_type=execution_type
        self.details=details
        self.started_at=now_datetime()
        self.started=time.monotonic()

    def finish(self,result="SUCCESS",retry_count=0,warning_count=0,failure_reason=None,next_retry=None,traceback=None,details=None):
        merged=dict(self.details or {})
        merged.update(details or {})
        return record(queue=self.queue,stage=self.stage,execution_type=self.execution_type,result=result,started_at=self.started_at,duration_ms=int((time.monotonic()-self.started)*1000),retry_count=retry_count,warning_count=warning_count,failure_reason=failure_reason,next_retry=next_retry,traceback=traceback,details=merged)
