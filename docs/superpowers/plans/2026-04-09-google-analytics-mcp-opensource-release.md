# Google Analytics MCP — Open Source Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare the Google Analytics MCP server for public open-source release with safe defaults, local STDIO auth without Firestore, 3 new tools, and a complete README matching the google-ads-mcp style.

**Architecture:** Two runtime modes are preserved unchanged — STDIO local mode (token stored in `~/.config/google-analytics-mcp/token.json`) and HTTP server mode (tokens in Firestore). The auth split lives in `oauth/google_auth.py`: if `current_user_email` ContextVar is set use Firestore, else check `MCP_USER_EMAIL` env var and load from local file. New tools follow the exact same pattern as existing tools in `server.py`.

**Tech Stack:** Python 3.10+, FastMCP, FastAPI, google-auth-oauthlib, google-auth, requests, python-dotenv

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `.gitignore` | Modify | Add `client_secret.json`, `.DS_Store` |
| `.env.example` | Create | Document all env vars with comments |
| `client_secret.json.example` | Create | Placeholder OAuth JSON so users know expected format |
| `oauth/google_auth.py` | Modify | Add `MCP_USER_EMAIL` fallback + local token file read/refresh |
| `setup_local_auth.py` | Create | One-shot script: browser OAuth flow → `~/.config/google-analytics-mcp/token.json` |
| `server.py` | Modify | Add `get_realtime_users`, `get_property_metadata`, `run_funnel_report` |
| `manifest.json` | Modify | Update author to dhawalshah, keep GoMarble attribution |
| `README.md` | Create | Full setup guide matching google-ads-mcp style |
| `tests/test_local_auth.py` | Create | Tests for the auth path split in google_auth.py |

---

## Task 1: Fix .gitignore and add example files

**Files:**
- Modify: `.gitignore`
- Create: `.env.example`
- Create: `client_secret.json.example`

- [ ] **Step 1: Update .gitignore**

Replace the contents of `.gitignore` with:

```
# Environment
.env

# OAuth credentials (never commit real credentials)
client_secret.json
*_token.json

# Python
__pycache__/
*.pyc
.venv/
lib/

# macOS
.DS_Store
```

- [ ] **Step 2: Create .env.example**

Create `.env.example`:

```env
# Path to your OAuth 2.0 client credentials JSON (downloaded from Google Cloud Console)
OAUTH_CONFIG_PATH=./client_secret.json

# Your Google Cloud Project ID — required for Firestore token storage (team/server mode only)
# Not needed for local STDIO mode (setup_local_auth.py stores tokens locally)
GCP_PROJECT_ID=your-gcp-project-id

# The Google Workspace domain allowed to log in (e.g. yourcompany.com)
# Only @ALLOWED_DOMAIN emails can authenticate (server mode only)
ALLOWED_DOMAIN=yourcompany.com

# Public URL of this service (server mode only)
# Local development: http://localhost:8080
# Cloud Run: https://your-service-name-xxxx.run.app
BASE_URL=http://localhost:8080

# Session secret key — use a long random string in production
# Generate one: python -c "import secrets; print(secrets.token_hex(32))"
SESSION_SECRET_KEY=change-me-to-a-long-random-string

# Local STDIO mode only: your Google account email
# Set this in your Claude Desktop MCP config env, not here
# MCP_USER_EMAIL=you@yourcompany.com
```

- [ ] **Step 3: Create client_secret.json.example**

Create `client_secret.json.example`:

```json
{
  "web": {
    "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
    "project_id": "YOUR_GCP_PROJECT_ID",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "YOUR_CLIENT_SECRET",
    "redirect_uris": [
      "http://localhost:8080/auth/callback"
    ]
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore .env.example client_secret.json.example
git commit -m "chore: fix gitignore, add env and credential examples"
```

---

## Task 2: Add local token support to oauth/google_auth.py

**Files:**
- Modify: `oauth/google_auth.py`
- Create: `tests/test_local_auth.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/__init__.py` (empty file), then create `tests/test_local_auth.py`:

```python
"""Tests for the auth path split in google_auth.py."""
import json
import os
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


def test_get_headers_uses_firestore_when_context_var_is_set():
    """HTTP server mode: current_user_email ContextVar → Firestore."""
    from oauth.google_auth import current_user_email, get_headers_with_auto_token

    mock_creds = MagicMock()
    mock_creds.token = "firestore-token"

    with patch("oauth.google_auth.load_token", return_value=mock_creds) as mock_load:
        token = current_user_email.set("user@example.com")
        try:
            headers = get_headers_with_auto_token()
        finally:
            current_user_email.reset(token)

    mock_load.assert_called_once()
    assert headers["Authorization"] == "Bearer firestore-token"


def test_get_headers_uses_local_token_when_env_var_set(tmp_path):
    """STDIO local mode: MCP_USER_EMAIL env var → local token file."""
    from oauth.google_auth import get_headers_with_auto_token, LOCAL_TOKEN_PATH

    mock_creds = MagicMock()
    mock_creds.token = "local-token"

    with patch.dict(os.environ, {"MCP_USER_EMAIL": "user@example.com"}):
        with patch("oauth.google_auth.load_local_token", return_value=mock_creds):
            headers = get_headers_with_auto_token()

    assert headers["Authorization"] == "Bearer local-token"


def test_get_headers_raises_when_no_auth():
    """No ContextVar, no env var → clear error message."""
    from oauth.google_auth import get_headers_with_auto_token

    env = {k: v for k, v in os.environ.items() if k != "MCP_USER_EMAIL"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(ValueError, match="No authenticated user"):
            get_headers_with_auto_token()


def test_load_local_token_returns_none_when_file_missing(tmp_path):
    """Returns None gracefully if token file doesn't exist."""
    from oauth import google_auth

    with patch.object(google_auth, "LOCAL_TOKEN_PATH", tmp_path / "nonexistent.json"):
        result = google_auth.load_local_token(["https://www.googleapis.com/auth/analytics.readonly"])

    assert result is None


def test_load_local_token_refreshes_expired_token(tmp_path):
    """Expired token is refreshed and saved back to disk."""
    from oauth import google_auth

    token_data = {
        "token": "old-token",
        "refresh_token": "refresh-token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "scopes": ["https://www.googleapis.com/auth/analytics.readonly"],
    }
    token_file = tmp_path / "token.json"
    token_file.write_text(json.dumps(token_data))

    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = "refresh-token"
    mock_creds.token = "new-token"

    with patch.object(google_auth, "LOCAL_TOKEN_PATH", token_file):
        with patch("oauth.google_auth.Credentials.from_authorized_user_info", return_value=mock_creds):
            with patch.object(mock_creds, "refresh"):
                result = google_auth.load_local_token(["https://www.googleapis.com/auth/analytics.readonly"])

    assert result is mock_creds
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/dhawal/src/team-mcp/google-analytics-mcp
pip install pytest -q
pytest tests/test_local_auth.py -v
```

Expected: multiple failures — `LOCAL_TOKEN_PATH` not defined, `load_local_token` not defined, existing `get_headers_with_auto_token` missing the new branches.

- [ ] **Step 3: Update oauth/google_auth.py**

Replace the full contents of `oauth/google_auth.py` with:

```python
"""
Google Analytics OAuth Authentication - multi-user server version.

Two auth paths:
  - HTTP server mode: current_user_email ContextVar is set by middleware in main.py
    → token loaded from Firestore
  - STDIO local mode: MCP_USER_EMAIL env var is set in Claude Desktop config
    → token loaded from LOCAL_TOKEN_PATH (~/.config/google-analytics-mcp/token.json)
"""

import json
import os
import contextvars
import logging
from pathlib import Path
from typing import Dict, Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError

from .firestore_tokens import load_token

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/analytics",
    "https://www.googleapis.com/auth/analytics.readonly",
]

LOCAL_TOKEN_PATH = Path.home() / ".config" / "google-analytics-mcp" / "token.json"

# Set by auth middleware in main.py for every HTTP request.
current_user_email: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_user_email", default=None
)


def load_local_token(scopes: list) -> Optional[Credentials]:
    """
    Load credentials from the local token file.
    Refreshes automatically if expired. Returns None if file missing or refresh fails.
    """
    if not LOCAL_TOKEN_PATH.exists():
        logger.warning(f"Local token file not found: {LOCAL_TOKEN_PATH}")
        return None

    try:
        token_data = json.loads(LOCAL_TOKEN_PATH.read_text())
        creds = Credentials.from_authorized_user_info(token_data, scopes)
    except Exception as e:
        logger.warning(f"Failed to load local token: {e}")
        return None

    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        try:
            logger.info("Refreshing local token...")
            creds.refresh(Request())
            LOCAL_TOKEN_PATH.write_text(creds.to_json())
            return creds
        except RefreshError:
            logger.warning("Local token refresh failed — re-run setup_local_auth.py")
            return None

    return None


def get_headers_with_auto_token() -> Dict[str, str]:
    """
    Get API headers for the current user.

    HTTP server mode: reads email from current_user_email ContextVar, loads token from Firestore.
    STDIO local mode: reads email from MCP_USER_EMAIL env var, loads token from local file.
    """
    email = current_user_email.get()

    if email:
        # HTTP server mode — use Firestore
        creds = load_token(email, SCOPES)
        if not creds:
            raise ValueError(
                f"No valid token for {email}. "
                "Please visit /auth/login to reconnect your Google account."
            )
    else:
        # STDIO local mode — use local token file
        email = os.environ.get("MCP_USER_EMAIL")
        if not email:
            raise ValueError(
                "No authenticated user found. "
                "For local use: set MCP_USER_EMAIL in your Claude Desktop config and run setup_local_auth.py. "
                "For team server: visit /auth/login."
            )
        creds = load_local_token(SCOPES)
        if not creds:
            raise ValueError(
                f"No valid local token for {email}. "
                "Run: python setup_local_auth.py"
            )

    return {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_local_auth.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add oauth/google_auth.py tests/__init__.py tests/test_local_auth.py
git commit -m "feat: add local token file auth path for STDIO mode"
```

---

## Task 3: Create setup_local_auth.py

**Files:**
- Create: `setup_local_auth.py`

This is a standalone script — it does NOT import from `oauth/`. It handles its own OAuth flow and writes the token file directly.

- [ ] **Step 1: Create setup_local_auth.py**

```python
#!/usr/bin/env python3
"""
One-shot local authentication for Google Analytics MCP (STDIO mode).

Starts a temporary HTTP server, opens your browser for Google OAuth consent,
and saves your token to ~/.config/google-analytics-mcp/token.json.

Usage:
    python setup_local_auth.py

Requirements:
    OAUTH_CONFIG_PATH env var (or ./client_secret.json by default)
"""

import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from google_auth_oauthlib.flow import Flow

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/analytics",
    "https://www.googleapis.com/auth/analytics.readonly",
]

REDIRECT_URI = "http://localhost:8080/auth/callback"
TOKEN_PATH = Path.home() / ".config" / "google-analytics-mcp" / "token.json"
CLIENT_CONFIG_PATH = os.environ.get("OAUTH_CONFIG_PATH", "./client_secret.json")

# Shared state between HTTP handler and main thread
_auth_code = None
_auth_error = None
_server_done = threading.Event()


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code, _auth_error
        parsed = urlparse(self.path)

        if parsed.path != "/auth/callback":
            self.send_response(404)
            self.end_headers()
            return

        params = parse_qs(parsed.query)
        if "error" in params:
            _auth_error = params["error"][0]
            self._respond("<h2>Authentication cancelled.</h2><p>You can close this tab.</p>")
        elif "code" in params:
            _auth_code = params["code"][0]
            self._respond(
                "<h2>Authentication successful!</h2>"
                "<p>You can close this tab and return to your terminal.</p>"
            )
        else:
            self._respond("<h2>Unexpected response.</h2>", status=400)

        _server_done.set()

    def _respond(self, body: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, format, *args):
        pass  # suppress request logs


def main():
    if not Path(CLIENT_CONFIG_PATH).exists():
        print(f"ERROR: OAuth credentials file not found: {CLIENT_CONFIG_PATH}")
        print("Set OAUTH_CONFIG_PATH or copy client_secret.json to this directory.")
        raise SystemExit(1)

    flow = Flow.from_client_secrets_file(
        CLIENT_CONFIG_PATH,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")

    server = HTTPServer(("localhost", 8080), _CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print("Opening browser for Google authentication...")
    print(f"If the browser doesn't open, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    _server_done.wait(timeout=120)
    server.shutdown()

    if _auth_error:
        print(f"ERROR: Authentication failed: {_auth_error}")
        raise SystemExit(1)

    if not _auth_code:
        print("ERROR: No authentication code received (timed out after 120s).")
        raise SystemExit(1)

    flow.fetch_token(code=_auth_code)
    creds = flow.credentials

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json())

    print(f"Token saved to: {TOKEN_PATH}")
    print("\nNext steps:")
    print("  Add to your Claude Desktop MCP config:")
    print('    "env": { "MCP_USER_EMAIL": "you@yourcompany.com", "OAUTH_CONFIG_PATH": "/path/to/client_secret.json" }')


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the script is importable (no syntax errors)**

```bash
python -c "import ast; ast.parse(open('setup_local_auth.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add setup_local_auth.py
git commit -m "feat: add setup_local_auth.py for local STDIO mode (no Firestore required)"
```

---

## Task 4: Add get_realtime_users to server.py

**Files:**
- Modify: `server.py`

Add this tool after the existing `get_device_metrics` tool and before `run_report`.

- [ ] **Step 1: Add get_realtime_users tool**

Insert the following block in `server.py` after the `get_device_metrics` function (after line 550) and before the `run_report` function:

```python
@mcp.tool
def get_realtime_users(
    property_id: str,
    dimensions: Optional[List[str]] = None,
    ctx: Context = None
) -> Dict[str, Any]:
    """Get active users in the last 30 minutes from Google Analytics 4.

    This uses the Realtime API — a different endpoint from standard reports.
    Data reflects activity within the last 30 minutes only; no date range applies.

    Args:
        property_id: Google Analytics 4 property ID (numeric, e.g., "123456789")
        dimensions: Dimensions to break down by (optional, defaults to ["unifiedScreenName"])
                   Other useful values: "country", "deviceCategory", "eventName"

    Returns:
        Active user counts per dimension value for the last 30 minutes
    """
    if ctx:
        ctx.info(f"Getting realtime users for property {property_id}...")

    try:
        headers = get_headers_with_auto_token()

        url = f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runRealtimeReport"

        payload = {
            "metrics": [{"name": "activeUsers"}]
        }

        if dimensions and len(dimensions) > 0:
            payload["dimensions"] = [{"name": dim} for dim in dimensions]
        else:
            payload["dimensions"] = [{"name": "unifiedScreenName"}]

        response = requests.post(url, headers=headers, json=payload)

        if not response.ok:
            if ctx:
                ctx.error(f"Google Analytics Realtime API error: {response.status_code} {response.reason}")
            raise Exception(f"Google Analytics Realtime API error: {response.status_code} {response.reason} - {response.text}")

        results = response.json()

        if not results.get("rows") or len(results.get("rows", [])) == 0:
            message = f"No active users in the last 30 minutes for property {property_id}"
            if ctx:
                ctx.info(message)
            return {"message": message, "activeUsers": 0}

        if ctx:
            ctx.info(f"Found {len(results.get('rows', []))} active user segments in realtime data.")

        return results

    except Exception as e:
        if ctx:
            ctx.error(f"Error getting realtime users: {str(e)}")
        raise
```

- [ ] **Step 2: Verify no syntax errors**

```bash
python -c "import ast; ast.parse(open('server.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add server.py
git commit -m "feat: add get_realtime_users tool (runRealtimeReport endpoint)"
```

---

## Task 5: Add get_property_metadata to server.py

**Files:**
- Modify: `server.py`

Add after `get_realtime_users` and before `run_report`.

- [ ] **Step 1: Add get_property_metadata tool**

Insert the following block in `server.py` after `get_realtime_users` and before `run_report`:

```python
@mcp.tool
def get_property_metadata(
    property_id: str,
    ctx: Context = None
) -> Dict[str, Any]:
    """List all valid dimensions and metrics available for a Google Analytics 4 property.

    Use this before calling run_report to discover which metric and dimension names
    are valid for a specific property. Different properties may have custom dimensions
    and metrics in addition to the standard GA4 ones.

    Args:
        property_id: Google Analytics 4 property ID (numeric, e.g., "123456789")

    Returns:
        Two lists — available dimensions and available metrics — each with name and description
    """
    if ctx:
        ctx.info(f"Fetching metadata for property {property_id}...")

    try:
        headers = get_headers_with_auto_token()

        url = f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}/metadata"

        response = requests.get(url, headers=headers)

        if not response.ok:
            if ctx:
                ctx.error(f"Google Analytics Metadata API error: {response.status_code} {response.reason}")
            raise Exception(f"Google Analytics Metadata API error: {response.status_code} {response.reason} - {response.text}")

        data = response.json()

        dimensions = [
            {
                "name": d.get("apiName", ""),
                "description": d.get("description", ""),
                "uiName": d.get("uiName", ""),
                "customDefinition": d.get("customDefinition", False),
            }
            for d in data.get("dimensions", [])
        ]

        metrics = [
            {
                "name": m.get("apiName", ""),
                "description": m.get("description", ""),
                "uiName": m.get("uiName", ""),
                "type": m.get("type", ""),
                "customDefinition": m.get("customDefinition", False),
            }
            for m in data.get("metrics", [])
        ]

        if ctx:
            ctx.info(f"Found {len(dimensions)} dimensions and {len(metrics)} metrics for property {property_id}.")

        return {
            "property_id": property_id,
            "dimensionCount": len(dimensions),
            "metricCount": len(metrics),
            "dimensions": dimensions,
            "metrics": metrics,
        }

    except Exception as e:
        if ctx:
            ctx.error(f"Error fetching property metadata: {str(e)}")
        raise
```

- [ ] **Step 2: Verify no syntax errors**

```bash
python -c "import ast; ast.parse(open('server.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add server.py
git commit -m "feat: add get_property_metadata tool (lists valid dimensions and metrics)"
```

---

## Task 6: Add run_funnel_report to server.py

**Files:**
- Modify: `server.py`

Add after `get_property_metadata` and before `run_report`.

- [ ] **Step 1: Add run_funnel_report tool**

Insert the following block in `server.py` after `get_property_metadata` and before `run_report`:

```python
@mcp.tool
def run_funnel_report(
    property_id: str,
    start_date: str,
    end_date: str,
    steps: List[Dict[str, Any]],
    breakdown_dimension: Optional[str] = None,
    ctx: Context = None
) -> Dict[str, Any]:
    """Run a funnel analysis report for a Google Analytics 4 property.

    ⚠️ EXPERIMENTAL: This uses the GA4 Data API v1alpha endpoint which is unstable
    and may break or change without notice.

    A funnel shows how many users complete each step in a sequence — e.g.
    homepage → product page → add to cart → purchase.

    Each step in `steps` must be a dict with:
      - "name": human-readable step label (e.g. "Homepage")
      - "filterExpression": a GA4 funnel filter expression dict

    STEP FORMAT EXAMPLES:

    Page path step:
    {
      "name": "Homepage",
      "filterExpression": {
        "funnelFieldFilter": {
          "fieldName": "pagePath",
          "stringFilter": {"matchType": "EXACT", "value": "/"}
        }
      }
    }

    Event step:
    {
      "name": "Purchase",
      "filterExpression": {
        "funnelEventFilter": {
          "eventName": "purchase"
        }
      }
    }

    Args:
        property_id: Google Analytics 4 property ID (numeric, e.g., "123456789")
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        steps: List of funnel step dicts (minimum 2 steps)
        breakdown_dimension: Optional dimension to break down funnel by (e.g. "deviceCategory")

    Returns:
        Funnel step data showing user counts and drop-off at each stage
    """
    if ctx:
        ctx.info(f"Running funnel report for property {property_id} ({len(steps)} steps)...")
        ctx.warning("Note: runFunnelReport is a v1alpha (experimental) endpoint and may change.")

    try:
        if not steps or len(steps) < 2:
            raise ValueError("steps must contain at least 2 funnel steps")

        headers = get_headers_with_auto_token()

        # v1alpha — experimental endpoint
        url = f"https://analyticsdata.googleapis.com/v1alpha/properties/{property_id}:runFunnelReport"

        payload = {
            "dateRanges": [{"startDate": start_date, "endDate": end_date}],
            "funnel": {
                "steps": steps
            },
        }

        if breakdown_dimension:
            payload["funnelBreakdown"] = {
                "breakdownDimension": {"dimensionName": breakdown_dimension}
            }

        response = requests.post(url, headers=headers, json=payload)

        if not response.ok:
            if ctx:
                ctx.error(f"GA4 Funnel API error: {response.status_code} {response.reason}")
            raise Exception(
                f"GA4 Funnel API error: {response.status_code} {response.reason} - {response.text}\n"
                "Note: runFunnelReport is experimental (v1alpha) and requires the property to have sufficient data."
            )

        results = response.json()

        if ctx:
            ctx.info("Funnel report completed.")

        return results

    except Exception as e:
        if ctx:
            ctx.error(f"Error running funnel report: {str(e)}")
        raise
```

- [ ] **Step 2: Verify no syntax errors**

```bash
python -c "import ast; ast.parse(open('server.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add server.py
git commit -m "feat: add run_funnel_report tool (v1alpha experimental)"
```

---

## Task 7: Update manifest.json

**Files:**
- Modify: `manifest.json`

- [ ] **Step 1: Update author and add new tools**

Replace the `author` block and `tools` array in `manifest.json`. The full updated file:

```json
{
  "dxt_version": "0.1",
  "name": "google-analytics-mcp",
  "display_name": "Google Analytics MCP",
  "version": "0.2.0",
  "description": "A Python MCP server for Google Analytics 4 API integration with OAuth 2.0 authentication",
  "long_description": "Connect Claude (or any MCP-compatible AI client) directly to your Google Analytics 4 properties. Supports historical reporting, real-time users, funnel analysis, property metadata, traffic sources, device metrics, and fully custom reports. Runs locally via STDIO (no cloud required) or as a shared team server on Google Cloud Run.",
  "author": {
    "name": "Dhawal Shah",
    "url": "https://github.com/dhawalshah"
  },
  "server": {
    "type": "python",
    "entry_point": "server.py",
    "mcp_config": {
      "command": "python",
      "args": [
        "${__dirname}/server.py"
      ],
      "env": {
        "OAUTH_CONFIG_PATH": "${user_config.oauth_config_path}",
        "MCP_USER_EMAIL": "${user_config.mcp_user_email}",
        "PYTHONPATH": "${__dirname}/lib"
      },
      "cwd": "${__dirname}"
    }
  },
  "tools": [
    {
      "name": "list_properties",
      "description": "List all Google Analytics 4 accounts with their associated properties"
    },
    {
      "name": "get_page_views",
      "description": "Get page view metrics for a date range"
    },
    {
      "name": "get_active_users",
      "description": "Get active user metrics for a date range"
    },
    {
      "name": "get_events",
      "description": "Get event metrics for a date range"
    },
    {
      "name": "get_traffic_sources",
      "description": "Get traffic source breakdown for a date range"
    },
    {
      "name": "get_device_metrics",
      "description": "Get device category metrics for a date range"
    },
    {
      "name": "get_realtime_users",
      "description": "Get active users in the last 30 minutes (Realtime API)"
    },
    {
      "name": "get_property_metadata",
      "description": "List all valid dimensions and metrics available for a property"
    },
    {
      "name": "run_funnel_report",
      "description": "Run a multi-step funnel analysis report (experimental v1alpha)"
    },
    {
      "name": "run_report",
      "description": "Execute a fully custom GA4 report with any metrics and dimensions"
    }
  ],
  "resources": [
    {
      "name": "ga4://reference",
      "description": "Google Analytics 4 API reference — metrics, dimensions, and examples"
    }
  ],
  "keywords": [
    "google",
    "analytics",
    "ga4",
    "web-analytics",
    "reporting",
    "metrics",
    "dimensions",
    "traffic",
    "users",
    "pageviews",
    "events",
    "realtime",
    "funnel",
    "oauth"
  ],
  "license": "MIT",
  "user_config": {
    "oauth_config_path": {
      "type": "string",
      "title": "OAuth Configuration Path",
      "description": "Full path to your Google Cloud OAuth 2.0 client credentials JSON file",
      "required": true,
      "sensitive": false
    },
    "mcp_user_email": {
      "type": "string",
      "title": "Your Google Account Email",
      "description": "Your Google account email — used to identify your stored credentials",
      "required": true,
      "sensitive": false
    }
  },
  "compatibility": {
    "claude_desktop": ">=0.10.0",
    "platforms": [
      "darwin",
      "win32",
      "linux"
    ],
    "runtimes": {
      "python": ">=3.10.0 <4"
    }
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add manifest.json
git commit -m "chore: update manifest — new author, add 3 new tools to tool list"
```

---

## Task 8: Write README.md

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README.md**

```markdown
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
| `run_funnel_report` | Multi-step funnel analysis — track drop-off across a user flow ⚠️ experimental (v1alpha) |
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
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README matching google-ads-mcp style"
```

---

## Task 9: Final verification

- [ ] **Step 1: Run all tests**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 2: Verify server.py parses and all 10 tools are registered**

```bash
python -c "
from server import mcp
tools = [t.name for t in mcp._tool_manager.list_tools()]
print('Tools:', tools)
expected = ['list_properties','get_page_views','get_active_users','get_events',
            'get_traffic_sources','get_device_metrics','get_realtime_users',
            'get_property_metadata','run_funnel_report','run_report']
missing = [t for t in expected if t not in tools]
print('Missing:', missing if missing else 'None — all good')
"
```

Expected output: all 10 tools listed, `Missing: None — all good`

- [ ] **Step 3: Verify client_secret.json is gitignored**

```bash
git check-ignore -v client_secret.json
```

Expected: `.gitignore:4:client_secret.json    client_secret.json`

- [ ] **Step 4: Final commit if any loose files**

```bash
git status
```

If clean: done. If any untracked/modified files remain, add and commit them.
```

Now let me do a self-review against the spec...

**Spec coverage check:**
- ✅ `.gitignore` fix — Task 1
- ✅ `.env.example` — Task 1
- ✅ `client_secret.json.example` — Task 1
- ✅ `oauth/google_auth.py` auth split — Task 2
- ✅ `setup_local_auth.py` — Task 3
- ✅ `get_realtime_users` — Task 4
- ✅ `get_property_metadata` — Task 5
- ✅ `run_funnel_report` — Task 6
- ✅ `manifest.json` update — Task 7
- ✅ `README.md` — Task 8
- ✅ Attribution in README — Task 8

**Placeholder scan:** No TBDs, no "implement later", no "similar to Task N". All code blocks are complete.

**Type consistency:** `LOCAL_TOKEN_PATH` defined in Task 2 and referenced in tests correctly. `load_local_token` defined in Task 2 and referenced in tests correctly. Tool functions all follow the same `get_headers_with_auto_token()` pattern.

All good. Let me save the plan.
