"""
Web routes that handle Google login for the GA MCP server.

/auth/login  → sends user to Google's login page
/auth/callback → Google sends user back here after login
/auth/status → shows who is logged in
/auth/logout → clears the session
"""

import os
import logging
import requests as http_requests
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from google_auth_oauthlib.flow import Flow

from .firestore_tokens import save_token

logger = logging.getLogger(__name__)

router = APIRouter()

SCOPES = [
    "https://www.googleapis.com/auth/analytics",
    "https://www.googleapis.com/auth/analytics.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

ALLOWED_DOMAIN = os.environ["ALLOWED_DOMAIN"]          # e.g. yourcompany.com
CLIENT_CONFIG_PATH = os.environ["OAUTH_CONFIG_PATH"]   # path to client_secret.json
BASE_URL = os.environ["BASE_URL"]                      # e.g. https://ga-mcp-xxx.run.app


def _make_flow(state=None):
    flow = Flow.from_client_secrets_file(
        CLIENT_CONFIG_PATH,
        scopes=SCOPES,
        redirect_uri=f"{BASE_URL}/auth/callback",
        state=state,
    )
    return flow


@router.get("/login")
async def login(request: Request):
    """Redirect the user to Google's login page."""
    flow = _make_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    request.session["oauth_state"] = state
    return RedirectResponse(auth_url)


@router.get("/callback")
async def callback(request: Request, code: str = None, state: str = None, error: str = None):
    """Google sends the user back here after they log in."""

    if error:
        return HTMLResponse(f"<h2>Login cancelled: {error}</h2><a href='/auth/login'>Try again</a>")

    saved_state = request.session.get("oauth_state")
    if not state or state != saved_state:
        return HTMLResponse("<h2>Security error: invalid state.</h2><a href='/auth/login'>Try again</a>", status_code=400)

    # Exchange the code for a token
    flow = _make_flow(state=state)
    flow.fetch_token(code=code)
    creds = flow.credentials

    # Get the user's email from Google
    user_info_resp = http_requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {creds.token}"},
    )
    user_info = user_info_resp.json()
    email = user_info.get("email", "")

    # Block anyone not on your company domain
    if not email.endswith(f"@{ALLOWED_DOMAIN}"):
        return HTMLResponse(
            f"<h2>Access denied.</h2>"
            f"<p>Only <strong>@{ALLOWED_DOMAIN}</strong> accounts can use this tool.</p>"
            f"<p>You logged in as: {email}</p>",
            status_code=403,
        )

    # Save their token to Firestore
    save_token(email, creds)

    # Remember them in the session cookie
    request.session["user_email"] = email
    logger.info(f"User logged in: {email}")

    return RedirectResponse("/auth/status")


@router.get("/status")
async def status(request: Request):
    """Shows who is currently logged in."""
    email = request.session.get("user_email")
    if not email:
        return HTMLResponse(
            "<h2>Not logged in</h2>"
            "<a href='/auth/login'><button>Login with Google</button></a>"
        )
    return HTMLResponse(
        f"<h2>✅ Logged in as {email}</h2>"
        f"<p>You can now connect Claude to this MCP server.</p>"
        f"<p><a href='/auth/logout'>Logout</a></p>"
    )


@router.get("/logout")
async def logout(request: Request):
    """Clear the session."""
    request.session.clear()
    return HTMLResponse("<h2>Logged out.</h2><a href='/auth/login'>Login again</a>")
