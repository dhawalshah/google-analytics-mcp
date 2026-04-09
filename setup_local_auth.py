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
