# Render Deployment Guide: Production 24×7 Always-Online MCP Server

This guide walks you through deploying your **Frappe CRM MCP Server** to **Render** (`https://render.com`) on the **Starter** plan for true **24×7 always-on operation**.

Once deployed, Google Gemini will query your production Frappe Cloud CRM 24/7, completely independent of your local PC, Windows, WSL, terminal, or network connection.

---

## 1. What is Pre-Configured in the Repository

The following files in your GitHub repository (`shahbazaman/visa_crm` on branch `main`) are already tuned for production:

1. **`render.yaml`**: Infrastructure Blueprint defining:
   - Service name: `visa-crm-mcp`
   - Runtime: `docker`
   - Region: `singapore` (closest to Middle East / UAE and India)
   - Plan: `starter` (always-on, 0% sleep, no cold starts)
   - Root directory: `frappe-mcp-server`
   - Health check path: `/health`
   - Auto deploy: `true`
2. **`frappe-mcp-server/Dockerfile`**: Production multi-stage container running as non-root `appuser` on dynamic `$PORT` with `/health` prober.
3. **`config.py`**: Configured for `*.onrender.com` domains with DNS rebinding protection and RFC 9728 / RFC 8414 OAuth 2.0 discovery.

---

## 2. Step-by-Step Deployment (2 Minutes)

### Step 1: Log in to Render
1. Go to **[https://render.com](https://render.com/)** and click **Log In** (or **Get Started**).
2. Sign in with your **GitHub account** (`shahbazaman`).

---

### Step 2: Create Web Service from GitHub Repository
1. On your Render Dashboard, click **New +** (top right) and select **Web Service**.
2. Under **"Connect a repository"**, select:
   * **`shahbazaman/visa_crm`**
3. Configure the parameters:
   * **Name**: `visa-crm-mcp`
   * **Region**: `Singapore`
   * **Branch**: `main`
   * **Root Directory**: `frappe-mcp-server`
   * **Runtime**: `Docker`
   * **Instance Type**: **Starter ($7/month)** (required for true 24×7 operation without container sleep)

---

### Step 3: Configure Environment Variables
In the **Environment Variables** section, configure the required variables:

| Key | Value | Description |
| :--- | :--- | :--- |
| `FRAPPE_BASE_URL` | `https://middleeast.frappe.cloud` | Production Frappe Cloud URL |
| `FRAPPE_API_KEY` | *(Your newly rotated Frappe API key)* | Read-only API Key |
| `FRAPPE_API_SECRET` | *(Your newly rotated Frappe API secret)* | Read-only API Secret |
| `GEMINI_CLIENT_ID` | `gemini-spark-client` | Dedicated OAuth Client ID |
| `GEMINI_CLIENT_SECRET` | *(Strong random 32-char secret)* | Client Secret for Gemini |
| `OAUTH_JWT_SECRET` | *(Strong random 32-char secret)* | JWT Signing Secret |
| `MCP_HOST` | `0.0.0.0` | Container bind address |
| `MCP_PUBLIC_URL` | `https://visa-crm-mcp.onrender.com` | Public HTTPS Base URL |

> [!IMPORTANT]
> Do NOT set `PORT`. Render automatically injects its dynamic `$PORT` into the running container.

---

### Step 4: Deploy & Verify
1. Click **Create Web Service**.
2. Render will build the Docker container from `frappe-mcp-server/Dockerfile` and start the service.
3. Once live, Render displays:
   ```text
   https://visa-crm-mcp.onrender.com
   ```
4. Verify by running the automated acceptance script:
   ```bash
   bash frappe-mcp-server/scripts/production_acceptance.sh
   ```

---

## 3. Connect Google Gemini Spark

1. Open **[Google Gemini](https://gemini.google.com)**.
2. Go to **Gemini → Spark → Custom Connected App → Edit / Add a custom app link**.
3. Enter your permanent Render URL:
   ```text
   https://visa-crm-mcp.onrender.com/mcp
   ```
4. Under **Advanced settings**:
   * **Client ID**: `gemini-spark-client`
   * **Client Secret**: `[YOUR_GEMINI_CLIENT_SECRET]`
5. Click **Save** / **Connect**.

---

## 4. Final PC-Off Acceptance Test

To verify true 24×7 autonomy:
1. Shut down your local development PC completely.
2. Ensure WSL and all terminals are closed.
3. From your mobile phone, open **Google Gemini**.
4. Ask:
   > *"Give me today's lead report from my Frappe CRM."*
   > *"Show me today's unassigned leads."*
   > *"Give me the management summary."*
5. Verify live CRM data is returned directly from `https://middleeast.frappe.cloud`.
