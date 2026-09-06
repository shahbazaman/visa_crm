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

## AI & MCP Architecture Distinction

### 1. Existing Pipeline (Frappe CRM -> Gemini API)
- **Direction**: Outbound from Frappe to Google Gemini API (`generativelanguage.googleapis.com`).
- **Trigger**: Automatic file uploads (call audio), background scheduler, communication events.
- **Components**: `visa_crm.api.gemini_service`, `visa_crm.api.ai_intelligence`.
- **Purpose**: Call audio transcription, sentiment evaluation, lead scoring, manager summaries, KPI tracking.

### 2. New Controlled MCP Pipeline (Gemini -> MCP Server -> Frappe CRM)
- **Direction**: Inbound queries from Gemini assistant to Frappe CRM.
- **Trigger**: Natural language user prompts (e.g. "Give me today's lead report from Frappe").
- **Components**:
  - Client: Google Gemini
  - Middleware: Controlled Model Context Protocol (MCP) Server
  - Backend API: `visa_crm.api.mcp.get_today_leads`
- **Security & Scope**:
  - Explicitly whitelisted and strictly read-only.
  - Requires authenticated session or token.
  - Enforces Frappe document permissions (`CRM Lead`).
  - Strict field whitelisting (`name`, `customer_name`, `email`, `phone`, `status`, `source`, `department`, `assigned_counselor`, `creation`).
  - No arbitrary SQL, no arbitrary DocType queries, no credential exposure.
