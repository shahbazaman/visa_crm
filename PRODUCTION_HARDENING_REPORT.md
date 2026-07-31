# Visa CRM Production Hardening Report

## Scope

This pass preserves the durable Meta stage orchestration and adds production controls around execution history, downstream enrichment, optional AI retries, counselor decisions, Android metadata ingestion, diagnostics, and validation.

## Implemented

- Added immutable `Pipeline Execution Log` records for scheduler runs, stage claims, successful completions, retries, stale lease recovery, worker recovery, AI dispatch, and AI completion/failure.
- Expanded Visa Application mapping from the durable normalized payload: visa type, country, destination, travel month, budget, passport status, notes, campaign source, campaign identifiers, and the full mapped-answer snapshot.
- Enriched Meta Communication Events with Lead, Customer360, Visa Application, Intake Queue, campaign/ad attribution, Facebook IDs, normalized payload snapshot, conversation identity, source channel, and processing timeline.
- Implemented persistent AI retry timing: 30 seconds, 2 minutes, 5 minutes, 10 minutes, 30 minutes, then hourly.
- Added AI retry history to Meta AI jobs and Call Intelligence.
- Added `CRM Lead.custom_ai_lead_score`, corrected invalid Lost Lead reason `Low Score` to allowed value `Other`, guaranteed ToDo descriptions, and added pre-insert AI document validation.
- Added metadata-first Android ingestion with companion JSON/description pairing, both upload orders, validation warnings, permanent raw JSON storage, employee/user matching, Customer360/Lead/Visa linking, SHA256 integrity checking, and `recording_id` idempotency.
- Kept legacy recordings compatible through delayed fallback when no companion metadata is received.
- Added metadata context to Gemini prompts so speaker identity, direction, duration, customer phone, and timestamps are not guessed.
- Expanded counselor selection with configurable round robin or least workload, language/country matching, working hours, holiday awareness, fallback counselor, and durable decision logs.
- Added the standard `Production Diagnostics` report and Call Intelligence metadata/integrity indicators.

## Database Changes

- New DocType: `Pipeline Execution Log`.
- New idempotent migration: `visa_crm.patches.production_hardening_meta_android`.
- New unique index: `uniq_vc_call_recording_id` on `Call Intelligence.recording_id`.
- New indexes: `idx_vc_execution_time`, `idx_vc_execution_queue`, and `idx_vc_android_pairing`.
- Additive Custom Fields on Call Intelligence, Communication Event, Visa Application, CRM Lead, Lead Intake AI Job, Lead Assignment, Counselor Assignment History, and Lost Lead Intelligence.
- Historical duplicate recording IDs are preserved and linked through `duplicate_of`; no records are deleted.

## Validation Evidence

- Python compilation: PASS.
- JSON schema parsing: PASS.
- `git diff --check`: PASS.
- First `bench --site local.test migrate`: PASS.
- Second `bench --site local.test migrate`: PASS.
- Direct idempotent patch rerun after indexes existed: PASS.
- Full Visa CRM suite: 59 tests, PASS.
- Android metadata focused tests: 7 tests, PASS.
- Production hardening focused tests: 3 tests, PASS.
- Downstream Visa/Communication idempotency test: PASS.
- Scheduler registration: active, enabled, cron `* * * * *`, bench-detectable.
- Production Diagnostics server execution: PASS.
- Android metadata pairing scheduler smoke test: PASS.
- Physical `recording_id` unique index verification: PASS.
- Execution history physical index verification: PASS.

## Existing Local Data Signals

The diagnostics report is intentionally reporting existing local operational debt rather than hiding it: old incomplete stage rows, assignment failures, and failed AI jobs remain visible and retryable. These historical records were not deleted or rewritten by this hardening pass.

## Deployment

Deploy code before migration. Frappe Cloud should run:

```bash
bench --site <site> migrate
bench --site <site> clear-cache
bench build --app visa_crm
bench restart
```

The migration is additive and safe to rerun. Existing Meta webhook payloads, durable queue records, CRM records, Android recordings, and historical execution data are preserved.
