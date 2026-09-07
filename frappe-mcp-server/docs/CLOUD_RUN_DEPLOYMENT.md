# Google Cloud Run Deployment Guide: 24/7 Always-Online MCP Server

This guide walks you through deploying your **Frappe CRM MCP Server** to **Google Cloud Run** so that **Google Gemini Spark** can query your Frappe Cloud CRM 24/7, completely independent of your local PC, Windows, WSL, or terminal.

---

## 1. Why Google Cloud Run?

* **Cost: $0.00 / month (Free Tier)**: Google Cloud Run provides:
  * 2,000,000 requests per month for free
  * 360,000 GB-seconds of memory free
  * 180,000 vCPU-seconds free
  * For Gemini CRM questions, your monthly bill will be **$0.00**.
* **Permanent Free HTTPS**: Automatic SSL certificate on `https://<service-name>-<hash>-<region>.run.app`.
* **Zero Local PC Dependency**: Runs inside Google's enterprise cloud infrastructure. You can power off your computer, close VS Code, and travel anywhere—Gemini will continue querying live Frappe Cloud CRM data.
* **Auto-Restart & Zero Maintenance**: Automatically restarts on failure, scales to meet traffic, and handles HTTP/2 and streaming MCP sessions.

---

## 2. Deployment Options

### Method A: Continuous Deployment from GitHub (Recommended — 2-Minute Setup in Web Browser)

Because your code is in GitHub (`https://github.com/shahbazaman/visa_crm.git`), Google Cloud can build and deploy it directly:

1. Open the **[Google Cloud Console](https://console.cloud.google.com/)**.
2. Search for **Cloud Run** in the top search bar and click **Create Service**.
3. Select **"Continuously deploy from a repository"** and click **Set up with Cloud Build**.
4. Select **GitHub** as your repository provider, authenticate, and choose repository:
   * **Repository**: `shahbazaman/visa_crm`
   * **Branch**: `main`
   * **Build Type**: `Dockerfile`
   * **Source location**: `/frappe-mcp-server/Dockerfile`
5. Configure the service:
   * **Service name**: `frappe-crm-mcp`
   * **Region**: `asia-south1` (Mumbai) or `us-central1` (low latency, lowest cost)
   * **Authentication**: Check **"Allow unauthenticated invocations"** (Gemini authenticates via OAuth 2.0 at the application layer)
   * **CPU allocation**: *CPU is only allocated during request processing* (serverless free tier)
   * **Min instances**: `0` (or `1` if you want instant zero-cold-start)
6. Under **Container, Networking, Security → Environment variables**, add:

| Variable Name | Value |
| :--- | :--- |
| `FRAPPE_BASE_URL` | `https://middleeast.frappe.cloud` |
| `FRAPPE_API_KEY` | *(Your Frappe Cloud API Key)* |
| `FRAPPE_API_SECRET` | *(Your Frappe Cloud API Secret)* |
| `GEMINI_CLIENT_ID` | `gemini-spark-client` |
| `GEMINI_CLIENT_SECRET` | `<YOUR_GEMINI_CLIENT_SECRET>` |
| `OAUTH_JWT_SECRET` | `<YOUR_OAUTH_JWT_SECRET>` |
| `MCP_HOST` | `0.0.0.0` |

7. Click **Create**.
8. Once deployed (approx. 1 minute), copy your permanent service URL:
   * Example: `https://frappe-crm-mcp-xxxxxx-as.a.run.app`
9. Edit your service variables to set:
   * `MCP_PUBLIC_URL` = `https://frappe-crm-mcp-xxxxxx-as.a.run.app`

---

### Method B: One-Line Deploy via Google Cloud SDK (`gcloud`)

If you have the `gcloud` CLI installed on any machine or Cloud Shell:

```bash
cd /home/shahbaz/frappe-bench/apps/visa_crm/frappe-mcp-server

gcloud run deploy frappe-crm-mcp \
  --source . \
  --region asia-south1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars="FRAPPE_BASE_URL=https://middleeast.frappe.cloud,FRAPPE_API_KEY=<YOUR_FRAPPE_API_KEY>,FRAPPE_API_SECRET=<YOUR_FRAPPE_API_SECRET>,GEMINI_CLIENT_ID=gemini-spark-client,GEMINI_CLIENT_SECRET=<YOUR_GEMINI_CLIENT_SECRET>,OAUTH_JWT_SECRET=<YOUR_OAUTH_JWT_SECRET>,MCP_HOST=0.0.0.0"
```

---

## 3. Verifying the Cloud Run Deployment

Test from anywhere (even from your phone):

```bash
# 1. Health check
curl -i https://<YOUR-CLOUD-RUN-URL>/health

# 2. OAuth Discovery
curl -i https://<YOUR-CLOUD-RUN-URL>/.well-known/oauth-authorization-server

# 3. Protected Resource Metadata
curl -i https://<YOUR-CLOUD-RUN-URL>/.well-known/oauth-protected-resource/mcp

# 4. Unauthenticated probe check (should return 401 with public WWW-Authenticate)
curl -i -X POST https://<YOUR-CLOUD-RUN-URL>/mcp
```

---

## 4. Final Gemini Spark Setup

In **[Google Gemini](https://gemini.google.com)**:

1. Go to **Gemini → Spark → Custom Connected App → Add a custom app link**.
2. Enter the permanent Cloud Run URL:
   ```text
   https://<YOUR-CLOUD-RUN-URL>/mcp
   ```
3. Under **Advanced settings**:
   * **Client ID**: `gemini-spark-client`
   * **Client Secret**: `<YOUR_GEMINI_CLIENT_SECRET>`
4. Click **Save** / **Connect**.

---

## 5. The Ultimate "PC Powered Off" Acceptance Test

1. **Power off your PC completely** (or close WSL and VS Code).
2. Open **Google Gemini** on your smartphone or any other computer.
3. Ask Gemini:
   > *"Give me today's lead report from my Frappe CRM."*
4. **Result**: Gemini connects directly to Google Cloud Run, queries live Frappe Cloud CRM (`https://middleeast.frappe.cloud`), and presents the real CRM data without touching your local PC.
