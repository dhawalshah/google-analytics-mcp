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
