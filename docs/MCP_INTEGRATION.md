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

### Pipeline B: New Inbound Conversational Integration (Gemini -> MCP -> Frappe)
* **Goal**: Enable Gemini to answer conversational business questions using verified production Frappe CRM data.
* **Flow**:
  ```
  User Prompt ("Give me today's lead report")
       ↓
  Google Gemini
       ↓
  MCP Server (Model Context Protocol)
       ↓  (Authenticated HTTPS)
  Frappe Whitelisted Endpoint (visa_crm.api.mcp.get_today_leads)
       ↓
  Production Database (CRM Lead)
  ```

---

## Phase 1 Implementation Status: VERIFIED

* **Endpoint**: `visa_crm.api.mcp.get_today_leads`
* **URL**: `https://middleeast.frappe.cloud/api/method/visa_crm.api.mcp.get_today_leads`
* **HTTP Method**: GET or POST
* **Authentication**: Required (Frappe Session Cookie or API Key/Secret token)
* **Permission**: `read` permission on `CRM Lead` (`Sales User`, `Sales Manager`, `System Manager`)
* **Output Schema**:
  ```json
  {
    "success": true,
    "date": "YYYY-MM-DD",
    "total": 8,
    "leads": [
      {
        "name": "CRM-LEAD-2026-00629",
        "customer_name": "Azna.fairuz",
        "email": null,
        "phone": "+918714889392",
        "status": "Qualified",
        "source": "Meta Instant Form",
        "department": "Holidays - MEH",
        "assigned_counselor": null,
        "creation": "2026-09-06 18:26:29.603265"
      }
    ]
  }
  ```

---

## Security Guarantees
1. **Zero Dynamic SQL**: No user or caller-supplied SQL execution.
2. **Fixed Business Entity**: Restricted entirely to `CRM Lead`.
3. **Field Whitelist**: Returns only verified business fields; omits credentials, tokens, or system passwords.
4. **Production Isolation**: Local test environments are completely bypassed; all validation happens on production.
