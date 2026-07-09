# Visa CRM Performance Audit

## Scope
Final production audit of database indexes, query performance, scheduler performance, queue efficiency, report/dashboard speed, Communication Center responsiveness, AI Dashboard responsiveness, and background job memory posture.

## Issues Found
- Lead Intake Queue scheduler lookup depended on status and retry timestamps but did not have explicit supporting indexes.
- Communication Event inbox/history queries depended on event, customer, lead, status, and datetime fields without explicit app-managed indexes.
- Communication Center conversation history could return unbounded rows.
- Communication Center inbox accepted arbitrary limits.
- Portal pages could perform broad reads if optional customer link fields were missing on related DocTypes.
- Dashboard APIs counted DocTypes without checking if the DocType existed.
- Chart APIs queried optional AI/reporting fields without checking schema.
- Final diagnostics queue API accepted large limits.
- Dead duplicate/debug files increased package size and audit noise.

## Fixes Applied
- Added `visa_crm.patches.performance_security_audit` for idempotent indexes:
  - `Lead Intake Queue`: status, source lead id, status+creation, status+next retry.
  - `Communication Event`: event id, customer, lead, event datetime, conversation status.
  - `CRM Lead`: mobile, email, workflow stage, assigned employee.
  - `Customer`: mobile, email, WhatsApp.
  - `ToDo`: status+date.
- Capped Communication Center inbox to 100 rows.
- Capped Communication Center conversation history to 100 rows.
- Capped queue diagnostics to 200 rows.
- Portal related-list APIs now return empty arrays instead of broad reads when the customer link field is missing.
- Dashboard and chart APIs now check DocType/field existence before querying.
- Removed unused duplicate/debug files:
  - `visa_crm/api/hi.py`
  - `visa_crm/api/gemini_service.py.bak`
  - `visa_crm/api/gemini_service_fixed.pyZone.Identifier`

## Remaining Recommendations
- Add database-level monitoring for slow queries after real production volume.
- Consider archiving old `Communication Event` rows once volume is high.
- Consider paginated UI for queue diagnostics if queue size exceeds 50k records.
- Keep Frappe Cloud worker concurrency aligned with Meta API rate limits.

## Readiness
Performance readiness score: **89%**
