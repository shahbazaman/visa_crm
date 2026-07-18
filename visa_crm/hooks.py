app_name = "visa_crm"
app_title = "Visa CRM"
app_publisher = "Shahbaz"
app_description = "Visa CRM AI Integration"
app_email = "shahbazaman2003@gmail.com"
app_license = "mit"
after_install = "visa_crm.install.after_install"
app_include_css = ["/assets/visa_crm/css/visa_crm.css","/assets/visa_crm/css/visa_portal.css"]
doc_events = {
    "File": {"after_insert": ["visa_crm.api.gemini_service.auto_create_call_intelligence"]},
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
        "before_save": ["visa_crm.api.crm_lifecycle.validate_lead_transition"],
        "after_save": ["visa_crm.api.crm_lifecycle.on_lead_update"]
    }
}
doctype_js = {
    "Call Intelligence": "public/js/call_intelligence.js",
    "Customer": "public/js/customer.js",
    "Communication Event": "public/js/communication_event.js",
    "CRM Lead": "public/js/crm_lead.js",
    "Visa Application": "public/js/visa_application.js",
    "Customer Documents": "public/js/customer_documents.js",
    "Payment Schedule": "public/js/payment_schedule.js"
}
doctype_list_js = {"CRM Lead": "public/js/crm_lead_list.js"}
scheduler_events = {
    "cron": {
        "* * * * *": [
            "visa_crm.api.gemini_service.process_unprocessed_audio_files",
            "visa_crm.api.intake_processor.process_pending"
        ],
        "*/10 * * * *": ["visa_crm.api.gemini_service.retry_failed_calls"],
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
page_js = {"manager-dashboard": "public/js/manager_dashboard.js"}
