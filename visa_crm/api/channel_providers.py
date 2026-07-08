import frappe
import requests
from visa_crm.api.meta_utils import safe_json_dumps

class ProviderError(Exception):
    pass

class BaseProvider:
    channel="Manual"
    def __init__(self, settings=None):
        self.settings=settings or frappe.conf
    def normalize_inbound(self,payload):
        payload=payload or {}
        return {"provider":self.channel,"provider_message_id":payload.get("id") or payload.get("message_id"),"phone":payload.get("phone") or payload.get("from"),"email":payload.get("email"),"content":payload.get("text") or payload.get("content") or payload.get("message"),"attachments":payload.get("attachments"),"raw_payload":payload}
    def send(self,to,content,**kwargs):
        return {"ok":True,"provider":self.channel,"to":to,"content":content,"meta":kwargs}
    def _post(self,url,headers,payload):
        res=requests.post(url,headers=headers,json=payload,timeout=20)
        if res.status_code>=300:
            raise ProviderError(f"{self.channel} send failed {res.status_code}: {res.text[:500]}")
        return res.json() if res.text else {"ok":True}

class WhatsAppCloudProvider(BaseProvider):
    channel="WhatsApp"
    def send(self,to,content,**kwargs):
        token=self.settings.get("whatsapp_access_token")
        phone_id=self.settings.get("whatsapp_phone_number_id")
        if not token or not phone_id:
            return super().send(to,content,**kwargs)
        url=f"https://graph.facebook.com/v20.0/{phone_id}/messages"
        payload={"messaging_product":"whatsapp","to":to,"type":"text","text":{"body":content}}
        return self._post(url,{"Authorization":f"Bearer {token}","Content-Type":"application/json"},payload)

class FacebookMessengerProvider(BaseProvider):
    channel="Messenger"
    def send(self,to,content,**kwargs):
        token=self.settings.get("facebook_page_access_token")
        if not token:
            return super().send(to,content,**kwargs)
        url=f"https://graph.facebook.com/v20.0/me/messages?access_token={token}"
        return self._post(url,{"Content-Type":"application/json"},{"recipient":{"id":to},"message":{"text":content}})

class InstagramDirectProvider(FacebookMessengerProvider):
    channel="Instagram"

class FacebookPageProvider(FacebookMessengerProvider):
    channel="Facebook"

class EmailProvider(BaseProvider):
    channel="Email"
    def send(self,to,content,**kwargs):
        frappe.sendmail(recipients=[to],subject=kwargs.get("subject") or "Visa CRM Update",message=content,now=False)
        return {"ok":True,"provider":self.channel,"to":to}

class PhoneProvider(BaseProvider):
    channel="Phone"

class AndroidCallProvider(BaseProvider):
    channel="Manual"
    def normalize_inbound(self,payload):
        data=super().normalize_inbound(payload)
        data.update({"source":"Android Call Recording","recording_file":payload.get("recording_file"),"duration":payload.get("duration")})
        return data

PROVIDERS={"whatsapp":WhatsAppCloudProvider,"messenger":FacebookMessengerProvider,"instagram":InstagramDirectProvider,"facebook":FacebookPageProvider,"facebook_page":FacebookPageProvider,"email":EmailProvider,"phone":PhoneProvider,"manual_phone":PhoneProvider,"android_call":AndroidCallProvider}

def get_provider(channel):
    return PROVIDERS.get((channel or "phone").lower(),PhoneProvider)()

def provider_log(event,**data):
    frappe.logger("visa_crm.communication").info(safe_json_dumps({"event":event,"data":data}))
