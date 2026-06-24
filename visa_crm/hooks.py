app_name = "visa_crm"
app_title = "Visa CRM"
app_publisher = "Shahbaz"
app_description = "Visa CRM AI Integration"
app_email = "shahbazaman2003@gmail.com"
app_license = "mit"


# FIX 1: Use after_insert for new Call Intelligence docs and after_save
#         only for manual recording_file attachment on existing records.
#         enqueue_processing skips unchanged saves and only queues when the
#         recording_file is newly added.
#
# FIX 2: Restored the missing File → after_insert hook so that audio files
#         uploaded via the File doctype automatically create a Call
#         Intelligence record and trigger processing.

doc_events = {

    "File": {
        "after_insert": [
            "visa_crm.api.gemini_service.auto_create_call_intelligence"
        ]
    },

    "Call Intelligence": {
        "after_insert": [
            "visa_crm.api.gemini_service.enqueue_processing"
        ],
        "after_save": [
            "visa_crm.api.gemini_service.enqueue_processing"
        ]
    }

}


doctype_js = {
    "Call Intelligence": "public/js/call_intelligence.js"
}


scheduler_events = {

    "cron": {

        # Picks up any audio files that were uploaded but not yet linked
        # to a Call Intelligence record (e.g. uploaded outside the UI).
        "* * * * *": [
            "visa_crm.api.gemini_service.process_unprocessed_audio_files"
        ],

        # Retries calls that failed upload or transcription (max 3 attempts).
        "*/10 * * * *": [
            "visa_crm.api.gemini_service.retry_failed_calls"
        ],
        "* * * * *":[
            "visa_crm.api.intake_processor.process_pending"
        ]

    },

    "daily": [
        "visa_crm.api.gemini_service.send_followup_reminders"
    ]

}
# override_whitelisted_methods={


# "meta.verify":"visa_crm.api.meta_webhook.verify",


# "meta.receive":"visa_crm.api.meta_webhook.receive"

# }
# fixtures = [

# "Custom Field",

# "Property Setter",

# "Client Script",

# "Server Script",

# "Workspace",

# "Workflow",

# "Workflow State",

# "Workflow Action Master",

# "Print Format"

# ]
fixtures=[

"Custom Field",

"Property Setter",

"Client Script",

"Server Script",

"Workspace",

"Workflow",

"Workflow State",

"Workflow Action Master",

"Print Format",

{
"dt":"DocType",
"filters":[
["module","=","Visa CRM"]
]
}

]