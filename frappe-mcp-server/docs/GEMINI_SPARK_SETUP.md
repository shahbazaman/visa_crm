# Connecting Google Gemini Spark to Frappe CRM MCP Server

This guide explains how to connect **Google Gemini Spark** (`gemini.google.com`) to the Frappe CRM MCP server via a Custom Connected App.

---

## 1. Overview & Architecture

```text
Google Gemini Spark (gemini.google.com)
       │
       ▼ (OAuth Discovery & Authentication)
Public MCP Endpoint: https://crm-mcp.<YOUR_DOMAIN>/mcp
       │
       ▼ (Cloudflare Tunnel)
127.0.0.1:8000 (Streamable HTTP Server)
       │
       ▼ (Controlled Read-Only Queries)
Production Frappe CRM (https://middleeast.frappe.cloud)
```

---

## 2. Configuration Settings for Gemini

In Google Gemini:
1. Open **Gemini** (`gemini.google.com`).
2. Go to **Settings** → **Connected Apps** (or **Gemini Spark** → **Add custom app link**).
3. Fill in the connection form:

| Setting | Value | Description |
| :--- | :--- | :--- |
| **App Name** | `Frappe CRM Assistant` | Human-readable name in your Gemini chat. |
| **MCP Server URL** | `https://crm-mcp.<YOUR_DOMAIN>/mcp` | The Streamable HTTP MCP endpoint. |

### Advanced Settings (OAuth 2.0 Credentials):
Click **Advanced settings** and enter:

| Setting | Value |
| :--- | :--- |
| **Client ID** | `gemini-spark-client` *(or your `GEMINI_CLIENT_ID` in `.env`)* |
| **Client secret** | `<YOUR_GEMINI_CLIENT_SECRET>` *(configured in `.env`)* |

> [!IMPORTANT]
> **NEVER** enter `FRAPPE_API_KEY`, `FRAPPE_API_SECRET`, or `MCP_AUTH_TOKEN` into Gemini.
> Gemini uses dedicated OAuth client credentials that communicate strictly with the MCP authorization server.

---

## 3. Natural Language Example Queries

Once connected, you can ask Gemini natural-language business questions:

1. **Today's Leads**:
   > *"Give me today's lead report from Frappe."*
   > *(Triggers `get_today_leads`)*

2. **Lead Volume**:
   > *"How many leads came into Frappe today?"*
   > *(Triggers `get_today_leads`)*

3. **Date Range / Weekly Report**:
   > *"Show me this week's leads report."*
   > *(Triggers `get_lead_report` with ISO dates)*

4. **Department Breakdown**:
   > *"Which departments received leads today?"*
   > *(Triggers `get_today_leads` or `get_leads_by_department`)*

5. **Unassigned Leads Backlog**:
   > *"Show me unassigned leads that need counselor allocation."*
   > *(Triggers `get_unassigned_leads`)*

6. **Today's Follow-ups**:
   > *"Show me today's follow-ups and scheduled calls."*
   > *(Triggers `get_followups`)*

7. **Visa Applications**:
   > *"How many visa applications were created this month?"*
   > *(Triggers `get_visa_applications`)*

8. **Executive Management Briefing**:
   > *"Give me a management summary for today."*
   > *(Triggers `get_management_summary`)*

---

## 4. Troubleshooting

- **"The MCP server could not be reached"**:
  - Verify your Cloudflare Tunnel is running (`systemctl status cloudflared-mcp` or `cloudflared tunnel run`).
  - Test health check: `curl -i https://crm-mcp.<YOUR_DOMAIN>/health`.
  - Ensure the URL ends in `/mcp`, not `/sse`.
- **"Invalid Client" or "Authentication Failed"**:
  - Double-check that the `Client ID` and `Client secret` match `GEMINI_CLIENT_ID` and `GEMINI_CLIENT_SECRET` in `.env`.
  - Check `/.well-known/oauth-authorization-server` in browser/curl to ensure discovery responds with HTTP 200.
