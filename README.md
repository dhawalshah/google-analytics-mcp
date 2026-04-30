# Google Analytics MCP

A Model Context Protocol (MCP) server for Google Analytics 4. Connect Claude (or any MCP-compatible AI client) directly to your GA4 properties to query traffic, analyse user behaviour, inspect events, run funnel analysis, and more — all in natural language.

The server speaks the [MCP authorization spec (2025-06-18)](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization), so it works as a remote connector for **Claude Teams** out of the box: the org owner adds **one URL**, each member clicks "Connect" and signs in with Google, done.

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

## How auth works

There are **two** modes. Pick one.

### Mode A — Local STDIO (one user, no server)
Use this if you only want it on your own machine. `setup_local_auth.py` runs the Google OAuth flow once and stores your token in `~/.config/google-analytics-mcp/token.json`. Claude Desktop launches `server.py` as a subprocess. No Firestore, no Cloud Run, no public URL.

### Mode B — Remote HTTP server (Claude Teams, claude.ai, multi-user)
The MCP server is also an OAuth 2.1 authorization server. When Claude connects:

1. Claude discovers our metadata at `/.well-known/oauth-protected-resource` and `/.well-known/oauth-authorization-server`.
2. Claude registers itself via Dynamic Client Registration (`POST /oauth/register`).
3. Claude redirects the user to `/oauth/authorize`. We delegate identification to Google OAuth.
4. After Google login, we issue our **own** opaque bearer token to Claude — Google credentials never leave the server.
5. On each `/mcp` request Claude sends our bearer; we map it server-side to the right user's stored Google credentials and call the GA4 APIs.

The `?user=email` query string from older versions is **gone** — there are no per-user URLs to copy around.

---

## Prerequisites

- Python 3.10+
- A Google Analytics 4 property
- A [Google Cloud](https://console.cloud.google.com/) project

---

## Step 1 — Set up Google Cloud

### 1a. Create a project and enable the GA4 APIs
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a project.
3. **APIs & Services → Library**, enable both:
   - **Google Analytics Data API**
   - **Google Analytics Admin API**

### 1b. Create OAuth 2.0 credentials
1. **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**.
2. Application type: **Web application**.
3. Add **Authorized redirect URIs**:
   - `http://localhost:8080/auth/callback` *(local dev / setup_local_auth.py)*
   - `https://YOUR-CLOUD-RUN-URL/auth/callback` *(remote deployment — add after deploy)*
4. Click **Create**, then **Download JSON** → save as `client_secret.json` in the project root *(gitignored)*. You can also copy the Client ID / Client Secret straight into env vars.

### 1c. OAuth consent screen
1. **APIs & Services → OAuth consent screen**.
2. Choose **Internal** for a Google Workspace org (recommended for teams), or **External** for personal/individual use.
3. Add scopes:
   - `https://www.googleapis.com/auth/analytics`
   - `https://www.googleapis.com/auth/analytics.readonly`
4. If using **External** in Testing mode, add each user's email under **Test users**.

### 1d. Enable Firestore *(Mode B only)*
The server stores OAuth bearer tokens and per-user Google credentials in Firestore.
1. In Cloud Console, **Firestore → Create database → Native mode**, pick a region.
2. Grant the Cloud Run service account **Cloud Datastore User** role under **IAM & Admin → IAM**.

---

## Step 2 — Install

```bash
git clone https://github.com/dhawalshah/google-analytics-mcp
cd google-analytics-mcp
pip install -r requirements.txt
cp .env.example .env       # fill in values
```

---

## Step 3 — Mode A: Local STDIO

```bash
python setup_local_auth.py
```

A browser opens, you sign in with Google, the script writes `~/.config/google-analytics-mcp/token.json`.

Then add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

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

Restart Claude Desktop. You're done — skip the rest.

---

## Step 3 — Mode B: Remote HTTP server (Claude Teams / claude.ai)

### Deploy to Cloud Run

```bash
gcloud run deploy google-analytics-mcp \
  --source . \
  --region YOUR_REGION \
  --project YOUR_PROJECT_ID \
  --platform managed \
  --port 8080 \
  --allow-unauthenticated \
  --set-env-vars "GCP_PROJECT_ID=your-project-id,BASE_URL=https://YOUR-SERVICE-URL.run.app,GOOGLE_CLIENT_ID=...,GOOGLE_CLIENT_SECRET=...,ALLOWED_DOMAINS=yourcompany.com"
```

> **Recommended:** store `GOOGLE_CLIENT_SECRET` as a [Cloud Run secret](https://cloud.google.com/run/docs/configuring/services/secrets) rather than a plain env var.

After it's up, go back to **APIs & Services → Credentials → your OAuth client** and add the live callback URL:

```
https://YOUR-SERVICE-URL.run.app/auth/callback
```

### Connect from Claude

**Claude Teams (org owner adds it once for everyone):**
- Settings → Connectors → Add custom connector
- URL: `https://YOUR-SERVICE-URL.run.app/mcp`
- Each member clicks **Connect**, signs in with Google, done.

**claude.ai personal:**
- Settings → Connectors → Add custom connector
- URL: `https://YOUR-SERVICE-URL.run.app/mcp`

**Claude Desktop with a remote server:**
```json
{
  "mcpServers": {
    "google-analytics": {
      "url": "https://YOUR-SERVICE-URL.run.app/mcp"
    }
  }
}
```
Claude Desktop will run the OAuth dance the first time you use it.

---

## Environment Variables

| Variable | Required | Description |
| --- | --- | --- |
| `BASE_URL` | Mode B | Public URL of this service. Used for OAuth metadata and as the canonical resource URI tokens are bound to. |
| `GCP_PROJECT_ID` | Mode B | GCP project hosting Firestore. |
| `GOOGLE_CLIENT_ID` | Mode B† | Google OAuth client ID. |
| `GOOGLE_CLIENT_SECRET` | Mode B† | Google OAuth client secret. |
| `OAUTH_CONFIG_PATH` | Mode B† | Alternative to the two above: path to `client_secret.json`. |
| `GOOGLE_REDIRECT_URI` | No | Override the Google callback URL. Defaults to `${BASE_URL}/auth/callback`. |
| `ALLOWED_DOMAINS` | No | Comma-separated email domain allowlist (e.g. `acme.com,beta.com`). Empty = no restriction. |
| `MCP_USER_EMAIL` | Mode A | Your email — set in Claude Desktop config. |
| `PORT` | No | HTTP port (default `8080`). |
| `LOG_LEVEL` | No | Python log level (default `INFO`). |

† Set **either** `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` **or** `OAUTH_CONFIG_PATH`.

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

## OAuth endpoint reference (Mode B)

For developers who want to verify the implementation or write their own MCP client.

| Endpoint | Spec | Purpose |
| --- | --- | --- |
| `GET /.well-known/oauth-protected-resource` | RFC 9728 | Advertises the canonical resource URI and authorization server. |
| `GET /.well-known/oauth-authorization-server` | RFC 8414 | Authorization server metadata. |
| `POST /oauth/register` | RFC 7591 | Dynamic Client Registration. |
| `GET /oauth/authorize` | OAuth 2.1 | Starts the auth code flow with PKCE; redirects to Google. |
| `GET /auth/callback` | — | Google redirects here; we mint our authorization code and bounce back to the MCP client. |
| `POST /oauth/token` | OAuth 2.1 | Authorization code + refresh token grants. |

A `GET /mcp` without a valid bearer returns `401` with a `WWW-Authenticate: Bearer resource_metadata="…"` header pointing at the protected-resource metadata document, which is how a standards-compliant MCP client discovers the rest.

---

## Attribution

Forked from [gomarble-ai/google-analytics-mcp-server](https://github.com/gomarble-ai/google-analytics-mcp-server), with additions:
- Local STDIO mode with token stored in `~/.config/google-analytics-mcp/token.json`
- `setup_local_auth.py` — one-shot local auth script
- Multi-user HTTP server mode acting as an OAuth 2.1 authorization server (DCR + PKCE + RFC 8707 resource indicators)
- Per-user OAuth token storage in Firestore
- Google Cloud Run deployment support
- 3 additional tools: realtime users, property metadata, funnel reports

---

## License

MIT
