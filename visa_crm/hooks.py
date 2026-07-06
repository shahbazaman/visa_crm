app_name = "visa_crm"
app_title = "Visa CRM"
app_publisher = "Shahbaz"
app_description = "Visa CRM AI Integration"
app_email = "shahbazaman2003@gmail.com"
app_license = "mit"
after_install = "visa_crm.install.after_install"
doc_events = {
    "File": {"after_insert": ["visa_crm.api.gemini_service.auto_create_call_intelligence"]},
    "Communication Event": {"before_insert": ["visa_crm.api.communication_event.auto_link"]},
    "Call Intelligence": {
        "after_insert": ["visa_crm.api.gemini_service.enqueue_processing"],
        "after_save": ["visa_crm.api.gemini_service.enqueue_processing"]
    }
}
doctype_js = {
    "Call Intelligence": "public/js/call_intelligence.js",
    "Customer": "public/js/customer.js",
    "Communication Event": "public/js/communication_event.js"
}
scheduler_events = {
    "cron": {
        "* * * * *": [
            "visa_crm.api.gemini_service.process_unprocessed_audio_files",
            "visa_crm.api.intake_processor.process_pending"
        ],
        "*/10 * * * *": ["visa_crm.api.gemini_service.retry_failed_calls"]
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
    "Workspace",
    "Workflow",
    "Workflow State",
    "Workflow Action Master",
    "Print Format",
    {"dt": "DocType", "filters": [["module", "=", "Visa CRM"]]}
]
page_js = {"manager-dashboard": "public/js/manager_dashboard.js"}
