# Visa CRM System Architecture

## Core Flow
Meta Instant Form -> Meta Webhook -> Lead Intake Queue -> Scheduler -> Meta Graph API -> CRM Lead -> Customer360 -> Counselor Assignment -> Communication Event -> Follow-up -> Dashboards.

## Production Boundaries
- Webhook only verifies Meta requests and queues intake records.
- Scheduler owns queue processing and retries.
- Customer360 owns duplicate matching.
- Gemini services own call intelligence and AI analysis.
- Diagnostics pages are read-only unless an Administrator runs an explicit admin tool.

## Diagnostic Pages
- Production Health: `/app/production-health`
- Lead Queue Diagnostics: `/app/lead-queue-diagnostics`
- Meta Diagnostics: `/app/meta-diagnostics`
- Scheduler Diagnostics: `/app/scheduler-diagnostics`
- Production Tools: `/app/production-tools`
