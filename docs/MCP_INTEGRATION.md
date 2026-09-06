# MCP (Model Context Protocol) Integration Guide

## Overview
This document outlines the phased implementation of the Model Context Protocol (MCP) bridge connecting Google Gemini to Frappe CRM.

---

## Architectural Separation of Concerns

### Pipeline A: Existing Outbound AI Integration (Frappe -> Gemini)
* **Components**: `visa_crm/api/gemini_service.py`, `visa_crm/api/ai_intelligence.py`.
* **Execution**: Frappe sends call audio or communication transcripts to Gemini 2.5 Flash API.
* **Output**: Structured transcription, sentiment analysis, employee evaluation, auto-lead creation.
* **Status**: Production active and untouched.

### Pipeline B: Inbound Conversational Integration (Gemini -> MCP -> Frappe)
* **Goal**: Enable Gemini to answer conversational business questions using verified production Frappe CRM data.
* **Flow**:
  ```
  User Prompt ("Give me today's lead report")
       ?
  Google Gemini (CLI / Antigravity / Agent)
       ?  (Stdio or HTTPS/SSE with Bearer Token)
  MCP Server (Model Context Protocol - frappe-mcp-server)
       ?  (Authenticated HTTPS: token <KEY>:<SECRET>)
  Frappe Whitelisted Endpoint (visa_crm.api.mcp.get_today_leads)
       ?
  Production Database (CRM Lead)
  ```

---

## Phase Status Summary

### Phase 1: Controlled Production API Endpoint (VERIFIED)
* **Endpoint**: `visa_crm.api.mcp.get_today_leads`
* **URL**: `https://middleeast.frappe.cloud/api/method/visa_crm.api.mcp.get_today_leads`
* **Security**: Blocks guest, verifies `read` permission on `CRM Lead`, dynamic schema resolution, 9-key projection.

### Phase 2: Standalone MCP Server & Stdio Integration (VERIFIED)
* **Server**: `frappe-mcp-server/` with `MCPServer("frappe-crm")`.
* **Tool**: `get_today_leads` (parameterless, read-only).
* **Verification**: Verified with live production data (8 leads returned), protocol handshake over Stdio, strict 9-field schema validated.

### Phase 3: Remote MCP Server & Dual-Transport Architecture (VERIFIED)
* **Transports Supported**:
  1. **Stdio**: Default local transport for IDEs.
  2. **SSE (Server-Sent Events)**: Network transport for remote Gemini clients via Uvicorn/Starlette.
* **Remote Security**:
  - `MCP_AUTH_TOKEN`: Protects `/sse` and `/messages/` with Bearer token authentication.
  - `/health`: Public health check returning operational status without credentials.
  - Server-side Frappe credentials remain completely hidden from remote clients.

---

## Security Guarantees
1. **Zero Dynamic SQL**: No user or caller-supplied SQL execution.
2. **Fixed Business Entity**: Restricted entirely to `CRM Lead`.
3. **Field Whitelist**: Returns only verified business fields; omits credentials, tokens, or system passwords.
4. **Credential Isolation**: Remote clients authenticate via `MCP_AUTH_TOKEN`; Frappe credentials are never sent across the MCP boundary.
