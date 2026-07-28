# Meta Integration Audit

- Active pipeline: `custom_visa_crm_only`
- Built-in CRM sync status: `not_found`
- Queue failure reason: `Error validating access token: Session has expired on Thursday, 09-Jul-26 04:00:00 PDT. The current time is Tuesday, 28-Jul-26 01:08:58 PDT.`
- App Review/config classification: `likely_token_or_oauth_configuration`

## Exact Graph API Response

```json
{"ok":false,"error":"Error validating access token: Session has expired on Thursday, 09-Jul-26 04:00:00 PDT. The current time is Tuesday, 28-Jul-26 01:08:58 PDT.","status_code":400,"request":{"url":"https://graph.facebook.com/v20.0/861435083391720","path":"861435083391720","params":{"fields":"id,created_time,field_data,form_id,ad_id,ad_name,adset_id,adset_name,campaign_id,campaign_name"}},"response":{"error":{"message":"Error validating access token: Session has expired on Thursday, 09-Jul-26 04:00:00 PDT. The current time is Tuesday, 28-Jul-26 01:08:58 PDT.","type":"OAuthException","code":190,"error_subcode":463,"fbtrace_id":"Afo193MfFhHPHsNDy5mgZqC","http_status":400},"status_code":400}}
```

## Remaining Blockers
- Meta Page ID is missing
- Meta lead form IDs are missing
- Graph API failure:Error validating access token: Session has expired on Thursday, 09-Jul-26 04:00:00 PDT. The current time is Tuesday, 28-Jul-26 01:08:58 PDT.

## Full Audit JSON

```json
{"official_crm_scheduler":{"method":"crm.lead_syncing.background_sync.sync_leads_from_all_enabled_sources","found":false,"rows":[],"active":false},"lead_sync_sources":{"doctype_exists":"Lead Sync Source","meta_rows":[],"other_enabled_rows":[]},"custom_pipeline":{"webhook":"visa_crm.api.meta_webhook.webhook","queue_doctype":"Lead Intake Queue","scheduler_method":"visa_crm.api.intake_processor.process_pending","scheduler_in_hooks":true,"active":true},"meta_settings":{"exists":true,"has_page_access_token":true,"page_id":null,"lead_form_ids":null,"has_app_secret":false,"has_verify_token":true},"latest_queue":{"name":"LIQ-2026-00001","status":"Processed","source_lead_id":"861435083391720","creation":"2026-07-09 15:32:25.323360","modified":"2026-07-09 15:32:25.323360","retry_count":5,"last_error":"","graph_payload":"{\"id\":\"861435083391720\",\"created_time\":\"2026-07-09T08:23:20+0000\",\"field_data\":[{\"name\":\"have_you_attended_the_canton_fair_before?\",\"values\":[\"<test lead: dummy data for have_you_attended_the_canton_fair_before?>\"]},{\"name\":\"do_you_have_a_valid_passport?\",\"values\":[\"<test lead: dummy data for do_you_have_a_valid_passport?>\"]},{\"name\":\"full_name\",\"values\":[\"<test lead: dummy data for full_name>\"]},{\"name\":\"phone\",\"values\":[\"<test lead: dummy data for phone>\"]},{\"name\":\"inbox_url\",\"values\":[\"<test lead: dummy data for inbox_url>\"]}],\"form_id\":\"2176710876449705\"}","graph_api_request":null,"graph_api_response":null,"page_id":null,"form_id":"2176710876449705","matched_lead":"CRM-LEAD-2026-00003","matched_customer":null,"communication_event":"COM-HR-EMP-00003-Lead--2026-07-09 15:39:48.439439","followup_reference":"0hten6791f"},"graph_probe":{"ok":false,"error":"Error validating access token: Session has expired on Thursday, 09-Jul-26 04:00:00 PDT. The current time is Tuesday, 28-Jul-26 01:08:58 PDT.","status_code":400,"request":{"url":"https://graph.facebook.com/v20.0/861435083391720","path":"861435083391720","params":{"fields":"id,created_time,field_data,form_id,ad_id,ad_name,adset_id,adset_name,campaign_id,campaign_name"}},"response":{"error":{"message":"Error validating access token: Session has expired on Thursday, 09-Jul-26 04:00:00 PDT. The current time is Tuesday, 28-Jul-26 01:08:58 PDT.","type":"OAuthException","code":190,"error_subcode":463,"fbtrace_id":"Afo193MfFhHPHsNDy5mgZqC","http_status":400},"status_code":400}},"blockers":["Meta Page ID is missing","Meta lead form IDs are missing","Graph API failure:Error validating access token: Session has expired on Thursday, 09-Jul-26 04:00:00 PDT. The current time is Tuesday, 28-Jul-26 01:08:58 PDT."],"active_pipeline":"custom_visa_crm_only","built_in_crm_sync_status":"not_found","queue_failure_reason":"Error validating access token: Session has expired on Thursday, 09-Jul-26 04:00:00 PDT. The current time is Tuesday, 28-Jul-26 01:08:58 PDT.","app_review_or_config":"likely_token_or_oauth_configuration"}
```
