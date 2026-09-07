# Render Deployment Guide: 100% Free, Always-Online MCP Server (No Credit Card Required)

This guide walks you through deploying your **Frappe CRM MCP Server** to **Render** (`https://render.com`) completely free with **zero credit card required**.

Once deployed, Google Gemini will query your production Frappe Cloud CRM 24/7, completely independent of your local PC, Windows, WSL, or terminal.

---

## 1. What is Pre-Configured for You

We have already configured and committed the following files to your GitHub repository (`shahbazaman/visa_crm` on branch `main`):

1. **`render.yaml`**: Infrastructure-as-code Blueprint that automatically defines the web service, Docker build path, health checks, and environment variables.
2. **`frappe-mcp-server/Dockerfile`**: Optimized production container running on port 8000/10000 with `/health` healthcheck.
3. **`config.py`**: Configured to accept traffic from `*.onrender.com` domains with DNS rebinding protection.

---

## 2. Step-by-Step Deployment (2 Minutes)

### Step 1: Sign up / Log in to Render
1. Go to **[https://render.com](https://render.com/)** and click **Get Started** (or **Log In**).
2. Sign in with your **GitHub account** (`shahbazaman`).  
   *(No credit card is asked for or required!)*

---

### Step 2: Create Web Service from GitHub Repository
1. On your Render Dashboard, click the **New +** button (top right) and select **Web Service**.
2. Under **"Connect a repository"**, select your repository:
   * **`shahbazaman/visa_crm`**
3. Configure the settings:
   * **Name**: `visa-crm-mcp` *(or any name you prefer)*
   * **Region**: `Singapore` *(recommended — closest to India / Middle East Frappe Cloud)*
   * **Branch**: `main`
   * **Root Directory**: `frappe-mcp-server`
   * **Runtime**: `Docker`
   * **Instance Type**: Select **Starter ($7/month)** for 24/7 continuous availability without sleeping, or **Free ($0/month)** for testing

---

### Step 3: Add Environment Variables
Scroll down to the **Environment Variables** section and click **Add Environment Variable** for each:

| Key | Value |
| :--- | :--- |
| `FRAPPE_BASE_URL` | `https://middleeast.frappe.cloud` |
| `FRAPPE_API_KEY` | `<YOUR_FRAPPE_API_KEY>` |
| `FRAPPE_API_SECRET` | `<YOUR_FRAPPE_API_SECRET>` |
| `GEMINI_CLIENT_ID` | `gemini-spark-client` |
| `GEMINI_CLIENT_SECRET` | `<YOUR_GEMINI_CLIENT_SECRET>` |
| `OAUTH_JWT_SECRET` | `<YOUR_OAUTH_JWT_SECRET>` |
| `MCP_HOST` | `0.0.0.0` |

---

### Step 4: Click Create Web Service
1. Click **Create Web Service** at the bottom.
2. Render will automatically pull the code from GitHub, build the Docker container, and start the service in about 1-2 minutes.
3. Once live, Render displays your permanent HTTPS URL at the top left under the service name:
   ```text
   https://visa-crm-mcp.onrender.com
   ```
4. Click **Environment** on the left menu, add one more variable:
   * `MCP_PUBLIC_URL` = `https://visa-crm-mcp.onrender.com`
   and click **Save Changes**.

---

## 3. Keep-Alive Tip for 100% Zero Cold Starts (Optional Free Bonus)

On Render's free tier, services spin down after 15 minutes of inactivity and take ~30 seconds to wake up on the next request.

To keep it **100% awake 24/7 with instant sub-second responses**:
1. Go to **[cron-job.org](https://cron-job.org)** or **[uptimerobot.com](https://uptimerobot.com)** (both 100% free forever, no card).
2. Add a simple HTTP monitor for:
   ```text
   https://visa-crm-mcp.onrender.com/health
   ```
   * Interval: Every **10 minutes**.
3. Render will never sleep, remaining active 24/7/365 for $0.00!

---

## 4. Final Google Gemini Spark Setup

Once your Render service is live:

1. Open **[Google Gemini](https://gemini.google.com)**.
2. Go to **Gemini → Spark → Custom Connected App → Edit / Add a custom app link**.
3. Enter your permanent Render URL:
   ```text
   https://visa-crm-mcp.onrender.com/mcp
   ```
4. Under **Advanced settings**:
   * **Client ID**: `gemini-spark-client`
   * **Client Secret**: `<YOUR_GEMINI_CLIENT_SECRET>`
5. Click **Save** / **Connect**.

---

## 5. The "PC Powered Off" Acceptance Test

1. Shut down your PC completely (or exit WSL).
2. Open **Google Gemini** on your phone or any other device.
3. Ask:
   > *"Give me today's lead report from my Frappe CRM."*
4. Gemini queries `https://visa-crm-mcp.onrender.com/mcp` directly in the cloud, retrieves live data from `https://middleeast.frappe.cloud`, and presents the real CRM results!
