# Android Call Metadata

Android uploads an audio file and a companion `CALL-YYYYMMDD-HHMMSS-XXXXXX_metadata.json` file. Visa CRM treats the Android JSON as the canonical call metadata source.

## Priority

1. Companion metadata JSON file
2. JSON in the Frappe `File.description`
3. Filename fallback for legacy recordings
4. Gemini extraction

Filename parsing never overwrites valid Android metadata.

## Pairing

The stable `CALL-YYYYMMDD-HHMMSS-XXXXXX` prefix and `recording_id` pair the two files. Either file may arrive first. Modern audio waits briefly for its companion metadata; the minute scheduler retries pairing and eventually enables legacy fallback if metadata never arrives.

`recording_id` is unique on Call Intelligence. Repeated uploads update and link the existing Call Intelligence record.

## Integrity

Visa CRM calculates the audio SHA256 and compares it with `sha256` or `file_hash` from Android. A mismatch is stored as an integrity warning and does not stop call processing.

## Required JSON

The validator expects `recording_id`, `employee_id`, `employee_name`, `customer_phone`, `call_direction`, positive `duration_seconds`, valid ISO8601 timestamps, `app_version`, and a valid SHA256 when supplied. Invalid metadata is retained unchanged in `android_metadata_json`, warnings are stored, and fallback processing continues.

## Idempotency

The immutable metadata JSON is saved once. Employee, Customer, CRM Lead, Visa Application, and Communication Event links are repaired when matching records become available. Retrying pairing or AI processing does not create another Call Intelligence record for the same `recording_id`.
