# Google Analytics MCP

A Model Context Protocol (MCP) server for Google Analytics 4. Connect Claude (or any MCP-compatible AI client) directly to your GA4 properties to query traffic, analyse user behaviour, inspect events, run funnel analysis, and more — all in natural language.

## What you can do

### Property Management
- List all accessible GA4 accounts and their properties

### Reporting & Analytics
- Page views, active users, events, traffic sources, and device metrics
- Run fully custom reports with any GA4 metric and dimension combination
- Funnel analysis — track user drop-off across multi-step flows *(experimental)*

### Real-time & Discovery
- Active users in the last 30 minutes (Realtime API)
- List all valid dimensions and metrics for a property — useful for building custom reports

---

## Prerequisites

- Python 3.10+
- A Google Analytics 4 property
- A [Google Cloud](https://console.cloud.google.com/) project

---

## Step 1: Set Up Google Cloud

### 1a. Create a project and enable the GA4 APIs

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Navigate to **APIs & Services → Library** and enable both:
   - **Google Analytics Data API**
   - **Google Analytics Admin API**

### 1b. Create OAuth 2.0 credentials

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth 2.0 Client IDs**
3. Choose **Web application**
4. Name it (e.g. `Google Analytics MCP`)
5. Under **Authorized redirect URIs**, add:
   - `http://localhost:8080/auth/callback` (for local setup and development)
   - `https://YOUR-CLOUD-RUN-URL/auth/callback` (for team/Cloud Run deployment — add after deploy)
6. Click **Create**, then **Download JSON**
7. Save the downloaded file as `client_secret.json` in your project root (this file is gitignored)

### 1c. Configure the OAuth consent screen

1. Go to **APIs & Services → OAuth consent screen**
2. Choose **Internal** if everyone using this is in your Google Workspace org (recommended for teams), or **External** for personal use
3. Fill in App Name (e.g. `Google Analytics MCP`), support email, and developer contact
4. Add scopes:
   - `https://www.googleapis.com/auth/analytics`
   - `https://www.googleapis.com/auth/analytics.readonly`
5. If using External in Testing mode, add each user's email under **Test users**

### 1d. Enable Firestore (team/Cloud Run mode only)

The server stores OAuth tokens in Firestore so each team member authenticates once and the token persists across restarts. Not needed for local single-user mode.

1. In Google Cloud Console, go to **Firestore**
2. Click **Create database**, choose **Native mode**, select a region
3. Grant the Cloud Run service account the **Cloud Datastore User** role under **IAM & Admin → IAM**

---

## Step 2: Local Setup

```bash
git clone https://github.com/dhawalshah/google-analytics-mcp
cd google-analytics-mcp
pip install -r requirements.txt
```

Copy and fill in your environment variables:

```bash
cp .env.example .env
```

Copy your OAuth credentials file (downloaded in Step 1b):

```bash
cp /path/to/downloaded-credentials.json client_secret.json
```

---

## Step 3: Authenticate

### Option A: Local single user

Run the local auth setup script. This opens your browser, completes the OAuth flow, and saves your token locally — no Firestore or GCP project needed.

```bash
python setup_local_auth.py
```

On success you'll see:
```
Token saved to: ~/.config/google-analytics-mcp/token.json
```

### Option B: Team server

Start the server and complete the OAuth flow via your browser:

```bash
python main.py
```

Open `http://localhost:8080/auth/login` and sign in with your Google account. Your token is saved to Firestore.

> Each team member who wants to use the MCP completes this step once from their own browser.

---

## Usage Options

### Option A: Local (Claude Desktop — single user)

After running `setup_local_auth.py`, add to your Claude Desktop config at `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "google-analytics": {
      "command": "python",
      "args": ["/absolute/path/to/google-analytics-mcp/server.py"],
      "env": {
        "OAUTH_CONFIG_PATH": "/absolute/path/to/client_secret.json",
        "MCP_USER_EMAIL": "you@yourcompany.com"
      }
    }
  }
}
```

Restart Claude Desktop.

---

### Option B: Team on Google Cloud Run

One deployment, always-on, each team member authenticates once via their browser.

**Prerequisites:** [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) installed and authenticated (`gcloud auth login`).

**1. Deploy to Cloud Run:**

```bash
gcloud run deploy google-analytics-mcp \
  --source . \
  --region YOUR_REGION \
  --project YOUR_PROJECT_ID \
  --platform managed \
  --port 8080 \
  --allow-unauthenticated \
  --set-env-vars "GCP_PROJECT_ID=your-project-id,ALLOWED_DOMAIN=yourcompany.com,SESSION_SECRET_KEY=your-secret-key,BASE_URL=https://YOUR-SERVICE-URL.run.app,OAUTH_CONFIG_PATH=/app/client_secret.json"
```

Replace `YOUR_REGION` (e.g. `asia-south1`), `YOUR_PROJECT_ID`, and `YOUR-SERVICE-URL`.

> **Recommended:** Store `client_secret.json` as a [Cloud Run secret](https://cloud.google.com/run/docs/configuring/services/secrets) rather than baking it into the image. Mount it at `/app/client_secret.json`.

**2. Add the Cloud Run callback URL to your OAuth credentials:**

Go back to **APIs & Services → Credentials → your OAuth client** and add:

```
https://YOUR-SERVICE-URL.run.app/auth/callback
```

**3. Each team member authenticates once:**

```
https://YOUR-SERVICE-URL.run.app/auth/login
```

**4. Connect via Claude Desktop:**

```json
{
  "mcpServers": {
    "google-analytics": {
      "url": "https://YOUR-SERVICE-URL.run.app/mcp?user=you@yourcompany.com"
    }
  }
}
```

---

## Environment Variables

| Variable | Required | Description |
| --- | --- | --- |
| `OAUTH_CONFIG_PATH` | Yes | Path to `client_secret.json` |
| `MCP_USER_EMAIL` | Local mode only | Your Google account email (set in Claude Desktop config) |
| `GCP_PROJECT_ID` | Team mode only | GCP project ID for Firestore token storage |
| `ALLOWED_DOMAIN` | Team mode only | Only `@ALLOWED_DOMAIN` emails can authenticate (e.g. `yourcompany.com`) |
| `BASE_URL` | Team mode only | Public URL of this service (e.g. `https://your-service.run.app`) |
| `SESSION_SECRET_KEY` | Team mode only | Secret for signing session cookies — use a long random string |
| `PORT` | No | HTTP port (default: `8080`) |

---

## Available Tools

| Tool | Description |
| --- | --- |
| `list_properties` | List all accessible GA4 accounts and their properties |
| `get_page_views` | Page views by path or any dimension for a date range |
| `get_active_users` | Active user counts by date or any dimension |
| `get_events` | Event counts by event name or any dimension |
| `get_traffic_sources` | Sessions and users by source/medium |
| `get_device_metrics` | Sessions and page views split by device category |
| `get_realtime_users` | Active users in the last 30 minutes (Realtime API) |
| `get_property_metadata` | List all valid dimensions and metrics for a property |
| `run_funnel_report` | Multi-step funnel analysis — track drop-off across a user flow *(experimental, v1alpha)* |
| `run_report` | Fully custom report — any GA4 metrics and dimensions |

---

## Example Prompts

```
Show me page views for the last 30 days

How many active users do we have right now?

What are our top traffic sources this month?

Which device type drives the most sessions?

Show me a funnel from homepage to purchase for last quarter

What custom dimensions does this property have?

Run a report showing sessions and bounce rate by country for January
```

---

## Attribution

Forked from [gomarble-ai/google-analytics-mcp-server](https://github.com/gomarble-ai/google-analytics-mcp-server), with additions:
- Local STDIO mode with token stored in `~/.config/google-analytics-mcp/token.json` (no Firestore needed)
- `setup_local_auth.py` — one-shot local auth script
- Multi-user HTTP server mode (FastAPI + session middleware)
- Per-user OAuth token storage in Firestore
- Google Cloud Run deployment support
- 3 additional tools: realtime users, property metadata, funnel reports

---

## License

MIT
