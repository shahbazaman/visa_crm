# Meta Pipeline

Visa CRM uses one custom Meta Lead Ads pipeline.

```text
Meta Webhook
-> Lead Intake Queue
-> Scheduler
-> Meta Graph API
-> Customer360
-> CRM Lead
```

## Webhook

Endpoint:

```text
/api/method/visa_crm.api.meta_webhook.webhook
```

The webhook accepts Meta verification by `GET` and lead events by `POST`.

Every incoming event is stored in `Meta Webhook Event` with event field, leadgen ID, page ID, form ID, raw JSON, sanitized request headers, and received timestamp.

## Event Types

`leadgen` is the only event that enters `Lead Intake Queue`.

`leadgen_update` is logged as a Meta webhook event and returns success, but it is not queued and is not sent to Graph API. This avoids fake test/update IDs such as `444444444444` and `987654321` becoming failed CRM leads.

## Queue

The queue stores source lead ID, event field, Page ID, Form ID, raw webhook payload, Graph request, Graph response, Graph error code, error subcode, error type, fbtrace ID, and message.

If Graph returns `Unsupported get request` or subcode `33` for an obvious dummy ID, the queue is marked `Ignored Test Event` and is not retried.

## Scheduler

The existing scheduler continues to run:

```text
visa_crm.api.intake_processor.process_pending
```

The scheduler processes only real queued `leadgen` events. It does not fetch Graph data for `leadgen_update`.

## Graph API

The app calls:

```text
GET https://graph.facebook.com/v20.0/{leadgen_id}
```

with:

```text
fields=id,created_time,field_data,form_id,page_id,ad_id,ad_name,adset_id,adset_name,campaign_id,campaign_name
```

Graph failures are saved with full diagnostic response so permission, OAuth, App Review, wrong Page/Form, or dummy test ID issues can be separated clearly.

## Diagnostics

APIs:

```text
visa_crm.api.meta_pipeline_audit.webhook_audit
visa_crm.api.meta_pipeline_audit.meta_health
visa_crm.api.meta_pipeline_audit.replay_webhook_event
```

Desk page:

```text
/app/meta-live-monitor
```

Replay uses stored webhook JSON and does not call Meta Graph API directly. Real CRM lead creation still requires a real `leadgen` event with retrievable Graph data.
