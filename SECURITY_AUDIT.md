# Visa CRM Security Audit

## Scope
Review of whitelisted APIs, guest access, permission checks, SQL injection safety, XSS posture, portal data isolation, admin utility exposure, logging consistency, and upload path validation.

## Issues Found
- Staff-facing APIs for Communication Center, dashboards, charts, manual intake, mobile inbox, and lead actions were whitelisted without explicit role checks.
- Production diagnostics read APIs exposed operational metadata to any logged-in user.
- Portal related-list functions could leak broad data if expected link fields were missing.
- Document upload registration accepted any file URL string.
- Communication Center query limits could be abused for large responses.
- One raw SQL helper used dynamic doctype/field interpolation, though values were internally selected.
- Meta webhook is guest-accessible by design and remains the primary public attack surface.

## Fixes Applied
- Added staff-role guards to:
  - `communication_center` inbox, conversation, updates, replies, templates.
  - `manual_intake.create_manual_lead`.
  - `mobile_api` staff inbox/thread/reply methods.
  - `lead_actions` form actions.
  - dashboard APIs.
  - chart APIs.
  - AI insights dashboard API.
- Added System Manager guard to production diagnostics APIs.
- Kept portal APIs scoped to the authenticated portal user's linked Customer.
- Portal related-list queries now fail closed if customer link fields are missing.
- Document upload registration now accepts only `/files/` or `/private/files/` paths.
- Query response limits added for Communication Center and diagnostics.
- Dashboard dynamic SQL now validates DocType and field metadata before query construction.

## Guest APIs
- `visa_crm.api.meta_webhook.webhook` remains `allow_guest=True` intentionally for Meta webhook verification and delivery.
- No new guest API was added in this audit.

## Remaining Recommendations
- Add upstream rate limiting/WAF rules for the Meta webhook endpoint on Frappe Cloud if available.
- Rotate Meta Page Access Token and App Secret regularly.
- Review System Manager membership before enabling production diagnostics.
- Consider adding per-user audit trails for Production Tools button usage.

## Readiness
Security readiness score: **87%**
