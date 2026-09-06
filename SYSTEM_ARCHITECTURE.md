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
- **Status**: Production active and 100% untouched.

### 2. Inbound Conversational MCP Pipeline (Gemini -> MCP Server -> Frappe CRM)
- **Direction**: Inbound queries from Gemini assistant to Frappe CRM.
- **Trigger**: Natural language user prompts (e.g. "Give me today's lead report from Frappe").
- **Components**:
  - Client: Google Gemini (Antigravity IDE, Gemini CLI, GenAI SDK agents)
  - Middleware: External Model Context Protocol (MCP) Server (`frappe-mcp-server/`)
  - Backend API: `visa_crm.api.mcp.get_today_leads` (`https://middleeast.frappe.cloud`)
- **Dual Transport Architecture (Phase 3)**:
  - **Local Transport**: Stdio via JSON-RPC 2.0 (zero network open ports, for local developer IDEs).
  - **Remote Transport**: Server-Sent Events (SSE) over HTTP/HTTPS with `/health` check and Bearer token authentication middleware (`MCP_AUTH_TOKEN`).
- **Security & Scope**:
  - Two-tier authentication: Remote clients authenticate with `MCP_AUTH_TOKEN`. Frappe credentials remain server-side only.
  - Explicitly whitelisted and strictly read-only (`get_today_leads`).
  - Enforces Frappe document permissions (`CRM Lead`).
  - Strict field whitelisting (`name`, `customer_name`, `email`, `phone`, `status`, `source`, `department`, `assigned_counselor`, `creation`).
  - No arbitrary SQL, no arbitrary DocType queries, no credential exposure.
