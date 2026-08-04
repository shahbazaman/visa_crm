import imaplib
import re
import smtplib
import socket
import ssl
import traceback
import frappe
from frappe import _
from frappe.email.smtp import InvalidEmailCredentials
from frappe.utils import cint

PROVIDERS={
    "GMail":{"service":"GMail","email_server":"imap.gmail.com","incoming_port":993,"use_ssl":1,"smtp_server":"smtp.gmail.com","smtp_port":587,"use_tls":1},
    "Outlook":{"service":"Outlook.com","email_server":"outlook.office365.com","incoming_port":993,"use_ssl":1,"smtp_server":"smtp.office365.com","smtp_port":587,"use_tls":1},
    "Sendgrid":{"service":"Sendgrid","smtp_server":"smtp.sendgrid.net","smtp_port":587,"use_tls":1,"outgoing_only":1},
    "SparkPost":{"service":"SparkPost","smtp_server":"smtp.sparkpostmail.com","smtp_port":587,"use_tls":1,"outgoing_only":1},
    "Yahoo":{"service":"Yahoo Mail","email_server":"imap.mail.yahoo.com","incoming_port":993,"use_ssl":1,"smtp_server":"smtp.mail.yahoo.com","smtp_port":587,"use_tls":1},
    "Yandex":{"service":"Yandex.Mail","email_server":"imap.yandex.com","incoming_port":993,"use_ssl":1,"smtp_server":"smtp.yandex.com","smtp_port":587,"use_tls":1},
}
SECRET_PATTERN=re.compile(r"(?i)(access[_ -]?token|refresh[_ -]?token|authorization|client[_ -]?secret|api[_ -]?secret|password)(\s*[:=]\s*)([^\s,;]+)")

class EmailSetupError(frappe.ValidationError):
    pass

class ConnectionStageError(Exception):
    def __init__(self,stage,error):
        self.stage=stage
        self.error=error
        super().__init__(str(error))

@frappe.whitelist()
def create_email_account(data:dict):
    data=frappe._dict(frappe.parse_json(data) if isinstance(data,str) else data or {})
    _validate_account_owner(data.get("email_id"))
    service=data.get("service")
    if service=="Frappe Mail":
        return _create_frappe_mail(data)
    config=PROVIDERS.get(service)
    if not config:
        frappe.throw(_("Unsupported email provider."),exc=EmailSetupError)
    _validate_input(data,config)
    doc=_build_account(data,config)
    try:
        checks=_test_connections(doc)
        doc.insert(ignore_permissions=True)
    except Exception as exc:
        stage=exc.stage if isinstance(exc,ConnectionStageError) else "account validation"
        cause=exc.error if isinstance(exc,ConnectionStageError) else exc
        diagnostic=classify_connection_error(cause,stage,service)
        _log_failure(diagnostic,cause,data)
        frappe.throw(diagnostic["message"],title=diagnostic["title"],exc=EmailSetupError)
    return {"ok":True,"name":doc.name,"provider":service,"checks":checks}

def _validate_account_owner(email_id):
    from visa_crm.api.lead_permissions import is_management,is_operational
    if not is_operational():
        frappe.throw(_("Visa CRM operational access is required."),frappe.PermissionError)
    if is_management():
        return
    allowed={str(frappe.session.user or "").strip().lower()}
    employee=frappe.db.get_value("Employee",{"user_id":frappe.session.user,"status":"Active"},["company_email","personal_email"],as_dict=True)
    if employee:
        allowed.update(str(employee.get(field) or "").strip().lower() for field in ("company_email","personal_email"))
    if str(email_id or "").strip().lower() not in {value for value in allowed if value}:
        frappe.throw(_("You may connect only an email address linked to your User or Employee record."),frappe.PermissionError)

@frappe.whitelist()
def diagnose_email_account(email_account,direction="both"):
    doc=frappe.get_doc("Email Account",email_account)
    doc.check_permission("write")
    directions=("incoming","outgoing") if direction=="both" else (direction,)
    if any(item not in ("incoming","outgoing") for item in directions):
        frappe.throw(_("Direction must be incoming, outgoing, or both."),exc=EmailSetupError)
    results={}
    for item in directions:
        try:
            _test_direction(doc,item)
            results[item]={"ok":True,"category":"connected"}
        except Exception as exc:
            diagnostic=classify_connection_error(exc,item,doc.service)
            _log_failure(diagnostic,exc,{"email_id":doc.email_id,"service":doc.service})
            results[item]={"ok":False,"category":diagnostic["category"],"message":diagnostic["message"]}
    return {"email_account":doc.name,"provider":doc.service,"auth_method":doc.auth_method,"oauth":oauth_readiness(doc),"results":results}

def oauth_readiness(doc):
    if doc.auth_method!="OAuth":
        return {"status":"not_applicable","configured":False}
    result={"status":"ready","configured":True,"connected_app":doc.connected_app,"connected_user":doc.connected_user,"redirect_uri":None,"https_redirect":False,"token_present":False,"refresh_available":False,"token_expired":None,"issues":[]}
    if not doc.connected_app:
        result["issues"].append("Connected App is missing")
    if not doc.backend_app_flow and not doc.connected_user:
        result["issues"].append("Connected User is missing")
    if result["issues"]:
        result.update({"status":"configuration_required","configured":False})
        return result
    try:
        app=frappe.get_doc("Connected App",doc.connected_app)
        result["redirect_uri"]=app.redirect_uri
        result["https_redirect"]=str(app.redirect_uri or "").startswith("https://")
        if not result["https_redirect"]:
            result["issues"].append("OAuth redirect URI is not HTTPS")
        user="" if doc.backend_app_flow else doc.connected_user
        token=app.get_token_cache(user)
        if token:
            result["token_present"]=_password_exists(token,"access_token")
            result["refresh_available"]=_password_exists(token,"refresh_token")
            result["token_expired"]=bool(token.is_expired())
        else:
            result["issues"].append("OAuth authorization is missing")
    except frappe.DoesNotExistError:
        result["issues"].append("Connected App does not exist")
    if result["issues"]:
        result.update({"status":"reconnect_required" if "OAuth authorization is missing" in result["issues"] else "configuration_required","configured":False})
    elif result["token_expired"] and result["refresh_available"]:
        result["status"]="refresh_required"
    elif result["token_expired"]:
        result.update({"status":"reconnect_required","configured":False})
    return result

def _validate_input(data,config):
    if not data.get("email_account_name"):
        frappe.throw(_("Account name is required."),exc=EmailSetupError)
    if not data.get("email_id"):
        frappe.throw(_("Email address is required."),exc=EmailSetupError)
    if not data.get("password"):
        frappe.throw(_("An App Password or provider-supported SMTP password is required."),exc=EmailSetupError)
    incoming=cint(data.get("enable_incoming"))
    outgoing=cint(data.get("enable_outgoing"))
    if not incoming and not outgoing:
        frappe.throw(_("Enable Incoming, Enable Outgoing, or both."),exc=EmailSetupError)
    if incoming and config.get("outgoing_only"):
        frappe.throw(_("{0} supports outgoing email only in this CRM setup.").format(data.service),exc=EmailSetupError)

def _build_account(data,config):
    incoming=cint(data.get("enable_incoming"))
    outgoing=cint(data.get("enable_outgoing"))
    password=_normalize_password(data.service,data.password)
    values={
        "doctype":"Email Account","email_id":data.email_id.strip(),"email_account_name":data.email_account_name.strip(),
        "service":config["service"],"auth_method":"Basic","enable_incoming":incoming,"enable_outgoing":outgoing,
        "default_incoming":incoming and cint(data.get("default_incoming")),"default_outgoing":outgoing and cint(data.get("default_outgoing")),
        "email_sync_option":"ALL","initial_sync_count":100,"create_contact":0,"track_email_status":1,
        "use_imap":incoming and not config.get("outgoing_only"),"email_server":config.get("email_server"),
        "incoming_port":config.get("incoming_port"),"use_ssl":config.get("use_ssl",0),"use_starttls":0,
        "smtp_server":config.get("smtp_server"),"smtp_port":config.get("smtp_port"),"use_tls":config.get("use_tls",0),
        "use_ssl_for_outgoing":0,"password":password,
    }
    if data.service=="Sendgrid":
        values["login_id_is_different"]=1
        values["login_id"]="apikey"
    doc=frappe.get_doc(values)
    if incoming:
        doc.append("imap_folder",{"folder_name":"INBOX"})
    if doc.meta.has_field("create_lead_from_incoming_email"):
        doc.create_lead_from_incoming_email=0
    return doc

def enforce_communication_only(doc,method=None):
    if doc.meta.has_field("create_lead_from_incoming_email"):
        doc.create_lead_from_incoming_email=0
    if doc.get("append_to")=="CRM Lead":
        doc.append_to=None
    for folder in doc.get("imap_folder") or []:
        if folder.get("append_to")=="CRM Lead":
            folder.append_to=None

def _create_frappe_mail(data):
    from crm.api.settings import create_email_account as standard_create
    try:
        return standard_create(data)
    except Exception as exc:
        diagnostic=classify_connection_error(exc,"account validation","Frappe Mail")
        _log_failure(diagnostic,exc,data)
        frappe.throw(diagnostic["message"],title=diagnostic["title"],exc=EmailSetupError)

def _test_connections(doc):
    results={}
    if doc.enable_incoming:
        try:
            _test_direction(doc,"incoming")
            results["incoming"]="connected"
        except Exception as exc:
            raise ConnectionStageError("incoming IMAP",exc) from exc
    if doc.enable_outgoing:
        try:
            _test_direction(doc,"outgoing")
            results["outgoing"]="connected"
        except Exception as exc:
            raise ConnectionStageError("outgoing SMTP",exc) from exc
    return results

def _test_direction(doc,direction):
    if direction=="incoming":
        if not doc.enable_incoming:
            frappe.throw(_("Incoming email is disabled for this account."),exc=EmailSetupError)
        doc.flags.validate_imap_pop_connection=True
        doc.get_incoming_server()
        return
    if not doc.enable_outgoing:
        frappe.throw(_("Outgoing email is disabled for this account."),exc=EmailSetupError)
    doc.validate_smtp_conn()

def _normalize_password(service,password):
    value=str(password or "")
    compact=re.sub(r"\s+","",value)
    if service=="GMail" and len(compact)==16 and compact.isalnum():
        return compact
    return value

def _password_exists(doc,fieldname):
    try:
        return bool(doc.get_password(fieldname,raise_exception=False))
    except Exception:
        return False

def classify_connection_error(exc,stage="connection",provider=None):
    text=str(exc or "")
    lowered=text.lower()
    category="configuration"
    title=_("Email Configuration Error")
    message=_("The email account configuration could not be validated.")
    if isinstance(exc,(InvalidEmailCredentials,smtplib.SMTPAuthenticationError)) or any(token in lowered for token in ("authenticationfailed","login failed","invalid credentials","username and password not accepted","535 5.7")):
        category="authentication"
        title=_("Email Authentication Failed")
        message=_("{0} authentication failed. Verify the complete mailbox address and its App Password, or use OAuth if required by the provider.").format(stage.title())
    if any(token in lowered for token in ("app password","application-specific password","login via your web browser","smtp auth disabled","basic authentication","modern authentication")):
        category="provider_policy"
        title=_("Email Provider Policy Blocked Authentication")
        message=_("The provider rejected {0} because of an account or organization security policy. Check App Password, IMAP, SMTP AUTH, and OAuth policy settings.").format(stage)
    if isinstance(exc,socket.gaierror):
        category="dns"
        title=_("Email Server DNS Failure")
        message=_("The email server hostname could not be resolved. Check the provider hostname and DNS availability.")
    elif isinstance(exc,(socket.timeout,TimeoutError)):
        category="timeout"
        title=_("Email Server Timeout")
        message=_("The {0} connection timed out. Check provider availability and hosting egress rules.").format(stage)
    elif isinstance(exc,ssl.SSLError):
        category="tls"
        title=_("Email TLS Verification Failed")
        message=_("The secure {0} connection failed certificate or TLS validation. Certificate verification was not disabled.").format(stage)
    elif isinstance(exc,(ConnectionRefusedError,smtplib.SMTPConnectError,smtplib.SMTPServerDisconnected)):
        category="connection"
        title=_("Email Server Connection Failed")
        message=_("The {0} server refused or closed the connection. Check hostname, port, TLS mode, and provider availability.").format(stage)
    elif "oauth" in lowered or "token" in lowered or "authorize" in lowered:
        category="oauth"
        title=_("Email OAuth Authorization Required")
        message=_("OAuth is missing, expired, or revoked. Reconnect the Email Account through its Connected App.")
    return {"category":category,"title":title,"message":message,"stage":stage,"provider":provider}

def redact_error(value,secrets=()):
    text=str(value or "")
    for secret in filter(None,(str(item) for item in secrets)):
        text=text.replace(secret,"[REDACTED]")
    return SECRET_PATTERN.sub(lambda match:f"{match.group(1)}{match.group(2)}[REDACTED]",text)

def _log_failure(diagnostic,exc,data):
    safe={"category":diagnostic["category"],"stage":diagnostic["stage"],"provider":diagnostic.get("provider"),"email":_mask_email(data.get("email_id")),"exception":type(exc).__name__,"detail":redact_error(exc,(data.get("password"),data.get("api_secret"))),"traceback":redact_error(traceback.format_exc(),(data.get("password"),data.get("api_secret")))}
    frappe.logger("visa_crm.email",allow_site=True,file_count=20).error(safe)

def _mask_email(value):
    value=str(value or "")
    if "@" not in value:
        return ""
    local,domain=value.rsplit("@",1)
    return f"{local[:2]}***@{domain}"
