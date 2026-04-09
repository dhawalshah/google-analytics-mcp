# Google Analytics MCP — Open Source Release Design

**Date:** 2026-04-09  
**Repo:** dhawalshah/google-analytics-mcp  
**Forked from:** gomarble-ai/google-analytics-mcp-server

---

## Goal

Prepare the Google Analytics MCP server for public open-source release on `dhawalshah/google-analytics-mcp`. This involves fixing the repo for safe public release (gitignore, env examples), improving local developer experience (STDIO mode with no Firestore required), adding 3 genuinely new tools, and writing a README that matches the style of `dhawalshah/google-ads-mcp`.

---

## Architecture

No structural changes to the existing codebase. `server.py` remains a single file. The two runtime modes are preserved:

- **STDIO mode** (`python server.py`) — local single-user, token stored in `~/.config/google-analytics-mcp/token.json`
- **HTTP server mode** (`python main.py`) — team/Cloud Run, tokens stored in Firestore

### Auth path split in `oauth/google_auth.py`

`get_headers_with_auto_token()` gains a second path:

```
current_user_email ContextVar set?
  YES → Firestore lookup (HTTP server mode, unchanged)
  NO  → check MCP_USER_EMAIL env var → local token file lookup
         if no email → raise "No authenticated user"
```

Local token file path: `~/.config/google-analytics-mcp/token.json`

---

## Files Changed

### Modified

| File | Change |
|---|---|
| `.gitignore` | Add `client_secret.json`, `.DS_Store` |
| `oauth/google_auth.py` | Add `MCP_USER_EMAIL` env var fallback + local token file read/write |
| `manifest.json` | Update author to dhawalshah, keep GoMarble in description attribution |
| `server.py` | Add 3 new tools |

### New

| File | Purpose |
|---|---|
| `.env.example` | Documents all env vars with inline comments |
| `client_secret.json.example` | Placeholder OAuth credentials JSON so users know the expected format |
| `setup_local_auth.py` | One-shot local auth script: opens browser, receives OAuth callback, saves token to `~/.config/google-analytics-mcp/token.json`. Requires only `OAUTH_CONFIG_PATH`. No Firestore. |
| `README.md` | Full setup guide matching google-ads-mcp style |

---

## New Tools (server.py)

### `get_realtime_users`
- **API:** `analyticsdata.googleapis.com/v1beta/properties/{id}:runRealtimeReport`
- **Why new:** Different endpoint from `runReport` — only way to get last-30-minute data
- **Params:** `property_id`, optional `dimensions` (defaults to `["unifiedScreenName"]`)
- **Returns:** Active user count per dimension value

### `get_property_metadata`
- **API:** `analyticsdata.googleapis.com/v1beta/properties/{id}/metadata`
- **Why new:** Lists all valid dimensions and metrics for a specific property — helps users build correct `run_report` calls without guessing names
- **Params:** `property_id`
- **Returns:** Two lists: available dimensions, available metrics (name + description for each)

### `run_funnel_report`
- **API:** `analyticsdata.googleapis.com/v1alpha/properties/{id}:runFunnelReport`
- **Why new:** Multi-step funnel analysis not possible with `runReport`
- **Stability:** v1alpha — experimental, can break without notice
- **Params:** `property_id`, `start_date`, `end_date`, `steps` (list of event/page filter dicts)
- **Returns:** User counts at each funnel step with drop-off

---

## setup_local_auth.py

Standalone script, no imports from the rest of the project except standard library + `google-auth-oauthlib`.

Flow:
1. Read `OAUTH_CONFIG_PATH` from env (or default `./client_secret.json`)
2. Create OAuth flow with GA4 scopes
3. Start a temporary `http.server` on `localhost:8080` to receive callback
4. Open browser to Google consent URL
5. Receive callback code, exchange for token
6. Save credentials to `~/.config/google-analytics-mcp/token.json`
7. Print success message with next steps, exit

Required env: `OAUTH_CONFIG_PATH` only.

---

## Local Token File

`oauth/google_auth.py` gains a `load_local_token(scopes)` function:
- Reads from `~/.config/google-analytics-mcp/token.json`
- Refreshes if expired (saves refreshed token back)
- Returns `None` if file doesn't exist or refresh fails

---

## .env.example

```env
# Path to your OAuth 2.0 client credentials JSON (downloaded from Google Cloud Console)
OAUTH_CONFIG_PATH=./client_secret.json

# Your Google Cloud Project ID — required for Firestore token storage (team/server mode only)
# Not needed for local STDIO mode
GCP_PROJECT_ID=your-gcp-project-id

# The Google Workspace domain allowed to log in (e.g. yourcompany.com)
# Only @ALLOWED_DOMAIN emails can authenticate (server mode only)
ALLOWED_DOMAIN=yourcompany.com

# Public URL of this service (server mode only)
# Local: http://localhost:8080 | Cloud Run: https://your-service.run.app
BASE_URL=http://localhost:8080

# Session secret — use a long random string in production
# Generate: python -c "import secrets; print(secrets.token_hex(32))"
SESSION_SECRET_KEY=change-me-to-a-long-random-string

# Local STDIO mode only: your Google account email
# Set this in your Claude Desktop MCP config env, not in .env
# MCP_USER_EMAIL=you@yourcompany.com
```

---

## README Structure

```
# Google Analytics MCP
<one-liner>

## What you can do
  Property Management / Reporting & Analytics / Real-time & Advanced

## Prerequisites

## Step 1: Set Up Google Cloud
  1a. Create project, enable Analytics Data API + Analytics Admin API
  1b. Create OAuth 2.0 credentials (Web application type)
  1c. Configure OAuth consent screen
  1d. Enable Firestore (team/Cloud Run mode only)

## Step 2: Local Setup
  git clone, pip install, cp .env.example .env

## Step 3: Authenticate
  Option A (local): python setup_local_auth.py
  Option B (team server): python main.py → visit /auth/login

## Usage Options
  Option A: Local — Claude Desktop STDIO with MCP_USER_EMAIL env var
  Option B: Team — Google Cloud Run deployment

## Environment Variables
  <table>

## Available Tools
  <table — run_funnel_report noted as experimental>

## Example Prompts

## Attribution

## License
```

---

## What Does NOT Change

- `main.py` — unchanged
- `oauth/auth_routes.py` — unchanged
- `oauth/firestore_tokens.py` — unchanged
- `Dockerfile` — unchanged
- `requirements.txt` — unchanged
- All existing 7 tools in `server.py` — unchanged

---

## Out of Scope

- Splitting `server.py` into modules
- Any write/mutation operations on GA4 properties
- Exploration reports (path exploration) — not available in GA4 public API
- Supporting non-Google-Workspace (personal Gmail) accounts in server mode
