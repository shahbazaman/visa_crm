PIPELINE_VERSION=2
STAGE_STATES=("NOT_STARTED","RUNNING","COMPLETED","FAILED","SKIPPED")
ORCHESTRATION_STATUSES=("PENDING","RUNNING","COMPLETED","COMPLETED_WITH_WARNINGS","PARTIALLY_COMPLETED","FAILED","IGNORED")
STAGES=(
    {"stage":"WEBHOOK","sequence":10,"requirement_class":"Core","max_attempts":1,"dependencies":()},
    {"stage":"GRAPH_DOWNLOAD","sequence":20,"requirement_class":"Core","max_attempts":5,"dependencies":("WEBHOOK",)},
    {"stage":"NORMALIZE","sequence":30,"requirement_class":"Core","max_attempts":5,"dependencies":("GRAPH_DOWNLOAD",)},
    {"stage":"CLASSIFICATION","sequence":35,"requirement_class":"Core","max_attempts":5,"dependencies":("NORMALIZE",)},
    {"stage":"CUSTOMER360","sequence":40,"requirement_class":"Core","max_attempts":5,"dependencies":("CLASSIFICATION",)},
    {"stage":"CRM_LEAD","sequence":50,"requirement_class":"Core","max_attempts":5,"dependencies":("CLASSIFICATION","CUSTOMER360")},
    {"stage":"LEAD_WORKFLOW","sequence":55,"requirement_class":"Required Downstream","max_attempts":5,"dependencies":("CRM_LEAD",)},
    {"stage":"VISA_APPLICATION","sequence":60,"requirement_class":"Required Downstream","max_attempts":5,"dependencies":("CRM_LEAD",)},
    {"stage":"COMMUNICATION_EVENT","sequence":70,"requirement_class":"Required Downstream","max_attempts":5,"dependencies":("CRM_LEAD",)},
    {"stage":"FOLLOW_UP","sequence":80,"requirement_class":"Required Downstream","max_attempts":5,"dependencies":("CRM_LEAD",)},
    {"stage":"COUNSELOR_ASSIGNMENT","sequence":90,"requirement_class":"Optional","max_attempts":0,"dependencies":("CRM_LEAD",)},
    {"stage":"AI_DISPATCH","sequence":100,"requirement_class":"Optional","max_attempts":0,"dependencies":("COMMUNICATION_EVENT",)},
    {"stage":"AI_GEMINI","sequence":110,"requirement_class":"Optional","max_attempts":0,"parent_stage":"AI_DISPATCH","dependencies":("AI_DISPATCH",)},
    {"stage":"AI_TRANSLATION","sequence":120,"requirement_class":"Optional","max_attempts":0,"parent_stage":"AI_DISPATCH","dependencies":("AI_GEMINI",)},
    {"stage":"AI_SUMMARY","sequence":130,"requirement_class":"Optional","max_attempts":0,"parent_stage":"AI_DISPATCH","dependencies":("AI_TRANSLATION",)},
    {"stage":"AI_EMBEDDING","sequence":140,"requirement_class":"Optional","max_attempts":0,"parent_stage":"AI_DISPATCH","dependencies":("AI_SUMMARY",)}
)
STAGE_BY_NAME={row["stage"]:row for row in STAGES}
BUSINESS_STAGES=tuple(row["stage"] for row in STAGES if not row["stage"].startswith("AI_"))
AI_STAGES=tuple(row["stage"] for row in STAGES if row["stage"].startswith("AI_"))
