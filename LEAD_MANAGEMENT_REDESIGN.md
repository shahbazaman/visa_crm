# Visa CRM Lead Management Redesign

## Verified Platform

- Frappe Framework: 15.110.0
- ERPNext: 15.110.0
- Frappe CRM: 1.73.0
- Visa CRM: 0.0.1

This implementation extends the existing resilient Lead Intake Queue pipeline. It does not create a second intake path and does not replace CRM Lead as the canonical operational lead.

## Data Ownership

| Concept | Canonical record | Notes |
| --- | --- | --- |
| Ingestion evidence | Lead Intake Queue | Raw payload, Graph response, normalized payload, source IDs, pipeline history |
| Operational lead | CRM Lead | Category, group, responsible department, assignment, Meta attribution |
| Customer identity | Customer / Customer360 services | Existing matching priority and idempotency are unchanged |
| Business processing | Visa Application | Continues to link to CRM Lead and Customer |
| Communication | Communication Event / Communication | Email is a channel, never a lead source |
| Follow-up | ToDo | Existing resilient follow-up stage is unchanged |

`source`, `lead_category`, `lead_group`, `responsible_department`, and assigned employee are intentionally separate fields.

## Pipeline Integration

Classification is the `CLASSIFICATION` stage in the existing stage ledger:

`WEBHOOK -> GRAPH_DOWNLOAD -> NORMALIZE -> CLASSIFICATION -> CUSTOMER360 -> CRM_LEAD`

All later Visa Application, Communication Event, Follow-up, assignment, and AI stages remain in the existing engine. The classification stage consumes the durable normalized payload and never calls Meta Graph API. A retry reuses manual classification and does not create business documents.

## Classification Fields

The migration adds these read-only Custom Fields to CRM Lead and Lead Intake Queue:

- `lead_category`
- `lead_group`
- `responsible_department`
- `classification_source`
- `classification_status`
- `classification_rule`
- `classification_reason`
- `classified_at`
- `classified_by`

Reclassification must use the Lead Management `Classify` action. Direct CRM Lead edits are rejected so `Lead Classification History` cannot be bypassed.

## Rule Precedence

Rules are stored in `Lead Classification Rule` and evaluated by ascending priority.

| Priority | Source | Match | Category | Active now |
| --- | --- | --- | --- | --- |
| 10 | WhatsApp | source equals WhatsApp | Reservation | Yes |
| 20 | Google Ads | source equals Google Ads | Google Ads | No |
| 100 | Meta | normalized campaign ends with `visa` | Global Visa | Yes |
| 110 | Meta | normalized campaign ends with `package` | Holidays | Yes |
| Fallback | Any | no enabled rule matches | Uncategorized | Always |

Normalization is Unicode NFKC, case-insensitive, punctuation-safe, underscore-safe, and whitespace-collapsing. Missing values never raise a classification error. Unmatched records use `Uncategorized`, group `Unspecified`, status `Needs Review`, and reason `No classification rule matched`.

The group is derived from durable destination, visa type, or country data first. When those are absent, the normalized campaign suffix is removed. If no reliable group remains, the group is `Unspecified`.

## Manual Overrides

Only management can call `visa_crm.api.lead_management.classify`. The operation:

1. Updates the existing CRM Lead without creating another lead.
2. Sets `classification_source` to `Manual`.
3. Records old/new category, old/new group, user, timestamp, and reason in `Lead Classification History`.
4. Updates the latest linked queue classification annotation.
5. Preserves source attribution and every business link.
6. Prevents scheduler retries from replacing the manual decision.

## Categories And Departments

Seeded categories are `Global Visa`, `Holidays`, `Reservation`, `Google Ads`, and `Uncategorized`. Google Ads has operational status `Future`; its ingestion rule is disabled.

Expected production department mappings are:

| Category | Department |
| --- | --- |
| Global Visa | Global visa - MEH |
| Holidays | Holidays - MEH |
| Reservation | Reservation - MEH |
| Google Ads | digital marketer - MEH |

The migration links a department only when that exact Department exists. It logs missing mappings instead of inventing Departments. `Uncategorized` is a shared safety queue for all operational roles. Additional category access can be granted explicitly with a User Permission for `Lead Category`.

## Permission Matrix

| User class | Category access | Lead access | Category configuration |
| --- | --- | --- | --- |
| System Manager / Administrator | All | All | Full |
| Sales Manager | All | All | Full |
| Configured management roles | All through protected APIs | All permitted by base DocPerm | Protected API |
| Sales User / Counselor / Visa Processing / Lead Team | Employee Department category, explicit User Permission categories, and Uncategorized | Backend-enforced category access | None |
| Inbox User | Mailbox owner data and permitted customer/lead communications | Only if also given a Visa CRM operational role | None |
| Unrelated ERPNext roles | Standard ERPNext behavior | Standard ERPNext behavior | None |

The custom category page intentionally queries through protected Visa CRM APIs because the installed Frappe CRM owner hierarchy otherwise limits list queries to owned/assigned records. Direct CRM Lead list/API queries remain at least as restrictive as standard CRM plus category conditions. Direct document access is checked by the backend hook; hiding cards is not the security boundary.

This site already had Custom DocPerm rows for CRM Lead. In Frappe, their presence replaces the standard DocPerm set; Sales User was absent and therefore had zero base Lead permission. The migration idempotently restores read/write/create/email/print/report/export for existing operational roles while leaving delete disabled. Category hooks then narrow the records available to each user.

## User Interface

The installed CRM SPA has no supported app route/component extension point for replacing `/crm/leads` without modifying upstream CRM source. To preserve upgrade compatibility, Visa CRM provides the native Desk page:

- `/app/lead-management`
- Visa CRM Workspace -> Lead Management
- CRM Lead Desk List -> Category View

The page displays category cards, groups, newest-first lead rows, search, unassigned/new/overdue/attention/pipeline indicators, and management classification controls. The management-only `All Leads` action opens the canonical CRM Lead list.

## Email Privacy

Email is communication-only and is not a Lead Category or intake source.

- New Email Accounts set `create_lead_from_incoming_email = 0` and `create_contact = 0`.
- IMAP folders are not appended to CRM Lead.
- Existing Email Accounts are repaired without deleting accounts, messages, or credentials.
- Operational users can connect only their User email or active Employee company/personal email; management can configure organizational accounts.
- Email Account list and direct document access are restricted to account owner, connected user, User Email mapping, or management.
- Unrelated Communication records are visible only to their mailbox owner or management.
- Customer/lead communications are visible only through an authorized CRM Lead/Deal context.
- Standard provider authentication, sending, receiving, TLS, passwords, and OAuth behavior are not changed by this redesign.

Operational email users require the standard `Inbox User` role in addition to their Visa CRM role so Frappe grants the base Email Account and Communication DocPerms. The Visa CRM hooks then narrow which records they can access.

## WhatsApp And Google Ads

Manual WhatsApp is recognized as a source only when a controlled intake record carries WhatsApp source metadata. There is no claim that manual phone WhatsApp conversations synchronize automatically.

The installed CRM contains WhatsApp UI/API support that activates only when a compatible WhatsApp app and settings are installed. Visa CRM does not add a competing Cloud API implementation. A future official integration must use secure webhook verification, provider message IDs for idempotency, Customer360 phone matching, existing-conversation attachment, and Reservation intake only for an unmatched identity.

Google Ads ingestion is not implemented or enabled. The inactive category and disabled source rule demonstrate that it can be activated later through configuration without changing the category model.

## Migration And Rollback

`visa_crm.patches.lead_management_redesign` is non-destructive and idempotent:

- Creates missing Custom Fields only and repairs their metadata when already present.
- Seeds missing categories/rules without replacing administrator configuration.
- Creates named non-unique query indexes only when physically absent.
- Backfills from durable queue/CRM Lead data without Graph calls.
- Reuses stage-ledger rows and marks the classification checkpoint.
- Never creates CRM Leads, Customers, Visa Applications, Communication Events, ToDos, or AI jobs.
- Never changes Facebook IDs or Meta campaign attribution.
- Never deletes historical queues or classification history.

Application rollback can remove the new hooks/page/API use while retaining the additive columns and classification records. Dropping fields or DocTypes is not part of rollback because preserving production data is safer.

## Deployment Verification

1. Run migration twice and confirm the second run makes no schema/data changes.
2. Map the production Departments to Lead Categories when exact names differ.
3. Give operational mailbox users `Inbox User` plus their departmental Visa CRM role.
4. Verify an employee sees only their mapped category and Uncategorized.
5. Verify a manager sees all categories and can classify an Uncategorized lead.
6. Retry a manually classified queue and verify the category is unchanged.
7. Verify original Meta IDs/campaign attribution and all Customer/Visa/Communication/ToDo links remain unchanged.
8. Verify one employee cannot list or open another employee's unrelated Email Account or Communication.
9. Verify a permitted customer email remains visible in the authorized lead timeline.
