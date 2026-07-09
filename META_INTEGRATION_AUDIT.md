# Meta Integration Audit

This report is generated at runtime by:

```bash
bench --site local.test execute visa_crm.api.meta_pipeline_audit.generate_report
```

The audit verifies:

- Official CRM scheduler method: `crm.lead_syncing.background_sync.sync_leads_from_all_enabled_sources`
- CRM `Lead Sync Source` Meta/Facebook/Instagram rows
- Custom Visa CRM pipeline: Meta Webhook -> Lead Intake Queue -> Intake Processor -> Customer360 -> CRM Lead
- Meta Settings presence, Page ID, lead form IDs, and Page Access Token presence
- Latest Lead Intake Queue status, failure reason, Graph request, and exact Graph response
- Whether the failure looks like App Review/permission restriction, OAuth/token configuration, wrong leadgen ID/page scope, or missing config

After migration, the app disables duplicate built-in CRM Meta sync sources when the custom Visa CRM pipeline is active. The patch does not remove CRM, does not remove CRM Lead, and does not alter Customer360, Gemini, Android uploads, lifecycle, or visa workflow.

Run the command above after receiving a real webhook. The generated file will include the exact Graph API response returned by Meta, which is the evidence needed to separate App Review restrictions from local configuration issues.
