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


def test_get_headers_uses_local_token_when_env_var_set():
    """STDIO local mode: MCP_USER_EMAIL env var → local token file."""
    from oauth.google_auth import get_headers_with_auto_token

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
    mock_creds.to_json.return_value = "{}"

    with patch.object(google_auth, "LOCAL_TOKEN_PATH", token_file):
        with patch("oauth.google_auth.Credentials.from_authorized_user_info", return_value=mock_creds):
            with patch.object(mock_creds, "refresh"):
                result = google_auth.load_local_token(["https://www.googleapis.com/auth/analytics.readonly"])

    assert result is mock_creds
