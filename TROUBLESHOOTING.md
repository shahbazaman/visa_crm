# Visa CRM Troubleshooting

## Queue Stuck
Check Lead Queue Diagnostics. Confirm status, retry count, last error, and next retry time.

## Meta Fetch Fails
Open Meta Diagnostics. Confirm token exists, Page ID is correct, and manually fetch one `leadgen_id`.

## Scheduler Not Running
Open Scheduler Diagnostics. Confirm last execution and pending jobs.

## Communication Center Error
Run migration and clear cache. The Communication Center API skips missing optional fields.

## AI Dashboard SQL Error
Run migration and clear cache. The AI dashboard checks fields before querying.

## Portal 404
Confirm `visa_crm/www/visa_portal.py` and `visa_crm/www/document_upload.py` exist and migrate has completed.
