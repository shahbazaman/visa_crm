import frappe
from visa_crm.api.communication_center import send_message

class NotificationService:
    channel="System"
    def send(self,to,subject,message,**kwargs):
        raise NotImplementedError

class WhatsAppNotification(NotificationService):
    channel="WhatsApp"
    def send(self,to,subject,message,**kwargs):
        return send_message("whatsapp",to,message,**kwargs)

class EmailNotification(NotificationService):
    channel="Email"
    def send(self,to,subject,message,**kwargs):
        frappe.sendmail(recipients=[to],subject=subject,message=message,now=False)
        return {"ok":True,"channel":self.channel}

class SystemNotification(NotificationService):
    channel="System"
    def send(self,to,subject,message,**kwargs):
        doc=frappe.new_doc("Notification Log")
        doc.subject=subject
        doc.email_content=message
        doc.for_user=to
        doc.type="Alert"
        if kwargs.get("document_type"):
            doc.document_type=kwargs.get("document_type")
        if kwargs.get("document_name"):
            doc.document_name=kwargs.get("document_name")
        doc.insert(ignore_permissions=True)
        return {"ok":True,"channel":self.channel,"name":doc.name}

class PushNotification(NotificationService):
    channel="Push"
    def send(self,to,subject,message,**kwargs):
        return {"ok":False,"channel":self.channel,"reason":"Push provider not configured"}

SERVICES={"whatsapp":WhatsAppNotification,"email":EmailNotification,"system":SystemNotification,"push":PushNotification}

def notify(channel,to,subject,message,**kwargs):
    return SERVICES.get((channel or "system").lower(),SystemNotification)().send(to,subject,message,**kwargs)
