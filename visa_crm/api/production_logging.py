import time
import frappe
from frappe.utils import now
from visa_crm.api.meta_utils import safe_json_dumps

def log_event(area,status,obj=None,error=None,traceback=None,duration_ms=None,**data):
    payload={"timestamp":now(),"area":area,"status":status,"object":obj,"duration_ms":duration_ms,"error":str(error) if error else None,"traceback":traceback or "","data":data}
    logger=frappe.logger("visa_crm.production")
    logger.error(safe_json_dumps(payload)) if status=="failed" else logger.info(safe_json_dumps(payload))
    return payload

class timed_log:
    def __init__(self,area,obj=None,**data):
        self.area=area; self.obj=obj; self.data=data; self.start=None
    def __enter__(self):
        self.start=time.time()
        log_event(self.area,"start",self.obj,**self.data)
        return self
    def __exit__(self,exc_type,exc,tb):
        duration=round((time.time()-self.start)*1000,2) if self.start else None
        if exc:
            log_event(self.area,"failed",self.obj,error=exc,traceback=frappe.get_traceback(),duration_ms=duration,**self.data)
        else:
            log_event(self.area,"success",self.obj,duration_ms=duration,**self.data)
        return False
