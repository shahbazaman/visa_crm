# Visa CRM Admin Guide

## Daily Checks
Open Production Health and confirm scheduler, queue, Meta API, and Gemini status.

## Queue Recovery
Use Lead Queue Diagnostics to inspect failed records. Use Production Tools -> Retry Queue for a specific queue record.

## Meta Testing
Use Meta Diagnostics to manually fetch a `leadgen_id`.

## Demo Data
Use Production Tools to generate demo lead, customer, visa application, communication event, payment, or follow-up without Meta API.

## Safety
Admin tools require System Manager and reuse existing pipeline APIs.
