app_name = "visa_crm"
app_title = "Visa CRM"
app_publisher = "Shahbaz"
app_description = "Visa CRM AI Integration"
app_email = "shahbazaman2003@gmail.com"
app_license = "mit"
after_install = "visa_crm.install.after_install"
app_include_css = ["/assets/visa_crm/css/visa_crm.css","/assets/visa_crm/css/visa_portal.css"]
after_migrate = "visa_crm.patches.disable_builtin_crm_meta_sync.enforce_builtin_crm_meta_sync_disabled"
override_doctype_class = {"Lead Sync Source": "visa_crm.overrides.lead_sync_source.VisaCRMLeadSyncSource"}
override_whitelisted_methods = {"crm.api.settings.create_email_account": "visa_crm.api.email_account.create_email_account"}
doc_events = {
    "File": {"after_insert": ["visa_crm.api.android_metadata.handle_file_upload","visa_crm.api.gemini_service.auto_create_call_intelligence"]},
    "Communication Event": {
        "before_insert": ["visa_crm.api.communication_event.auto_link"],
        "after_insert": ["visa_crm.api.communication_center.after_communication_insert"]
    },
    "Call Intelligence": {
        "before_insert": ["visa_crm.api.gemini_service.prevent_duplicate_call_intelligence"],
        "after_insert": ["visa_crm.api.gemini_service.enqueue_processing"],
        "after_save": ["visa_crm.api.gemini_service.enqueue_processing"]
    },
    "CRM Lead": {
        "before_insert": ["visa_crm.api.lead_creator.log_crm_lead_hook"],
        "autoname": ["visa_crm.api.lead_creator.log_crm_lead_hook"],
        "before_validate": ["visa_crm.api.lead_classification.protect_lead_classification", "visa_crm.api.lead_creator.log_crm_lead_hook"],
        "validate": ["visa_crm.api.lead_creator.log_crm_lead_hook"],
        "before_save": ["visa_crm.api.crm_lifecycle.validate_lead_transition", "visa_crm.api.lead_creator.log_crm_lead_hook"],
        "after_insert": ["visa_crm.api.lead_creator.log_crm_lead_hook"],
        "after_save": ["visa_crm.api.crm_lifecycle.on_lead_update"]
    },
    "Lead Sync Source": {"before_validate": ["visa_crm.patches.disable_builtin_crm_meta_sync.prevent_builtin_meta_sync_enable"]},
    "Email Account": {"before_validate": ["visa_crm.api.email_account.enforce_communication_only"]}
}
permission_query_conditions = {
    "CRM Lead": "visa_crm.api.lead_permissions.crm_lead_query",
    "Lead Intake Queue": "visa_crm.api.lead_permissions.queue_query",
    "Customer": "visa_crm.api.lead_permissions.customer_query",
    "Visa Application": "visa_crm.api.lead_permissions.visa_query",
    "Communication Event": "visa_crm.api.lead_permissions.communication_event_query",
    "ToDo": "visa_crm.api.lead_permissions.todo_query",
    "Email Account": "visa_crm.api.lead_permissions.email_account_query",
    "Communication": "visa_crm.api.lead_permissions.communication_query"
}
has_permission = {
    "CRM Lead": "visa_crm.api.lead_permissions.crm_lead_permission",
    "Lead Intake Queue": "visa_crm.api.lead_permissions.queue_permission",
    "Customer": "visa_crm.api.lead_permissions.customer_permission",
    "Visa Application": "visa_crm.api.lead_permissions.visa_permission",
    "Communication Event": "visa_crm.api.lead_permissions.communication_event_permission",
    "ToDo": "visa_crm.api.lead_permissions.todo_permission",
    "Email Account": "visa_crm.api.lead_permissions.email_account_permission",
    "Communication": "visa_crm.api.lead_permissions.communication_permission"
}
doctype_js = {
    "Call Intelligence": "public/js/call_intelligence.js",
    "Customer": "public/js/customer.js",
    "Communication Event": "public/js/communication_event.js",
    "CRM Lead": "public/js/crm_lead.js",
    "Visa Application": "public/js/visa_application.js",
    "Customer Documents": "public/js/customer_documents.js",
    "Payment Schedule": "public/js/payment_schedule.js",
    "Email Account": "public/js/email_account.js"
}
doctype_list_js = {"CRM Lead": "public/js/crm_lead_list.js"}
scheduler_events = {
    "cron": {
        "* * * * *": [
            "visa_crm.api.gemini_service.process_unprocessed_audio_files",
            "visa_crm.api.android_metadata.process_pending_metadata_pairs",
            "visa_crm.api.gemini_service.retry_failed_calls",
            "visa_crm.api.intake_processor.process_pending"
        ],
        "0 * * * *": ["visa_crm.api.crm_lifecycle.process_overdue_followups"]
    },
    "daily": [
        "visa_crm.api.gemini_service.send_followup_reminders",
        "visa_crm.api.reminder_scheduler.create_reminders"
    ]
}
fixtures = [
    "Custom Field",
    "Property Setter",
    "Client Script",
    "Server Script",
    "Workflow",
    "Workflow State",
    "Workflow Action Master",
    {"dt": "DocType", "filters": [["module", "=", "Visa CRM"]]}
]
page_js = {
    "manager-dashboard": "public/js/manager_dashboard.js",
    "lead-management": "visa_crm/page/lead_management/lead_management.js"
}
website_redirects = [
    {"source": "/crm/leads/view/list", "target": "/app/lead-management"}
]
