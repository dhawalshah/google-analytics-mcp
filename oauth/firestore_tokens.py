"""
Stores and retrieves per-user OAuth tokens in Firestore.
Each user's token is saved under their email address.
"""

import json
import os
import logging
from google.cloud import firestore
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError

logger = logging.getLogger(__name__)

COLLECTION = "user_tokens_ga"  # separate collection per MCP


def _db():
    return firestore.Client(project=os.environ["GCP_PROJECT_ID"])


def save_token(user_email: str, creds: Credentials):
    """Save a user's credentials to Firestore."""
    _db().collection(COLLECTION).document(user_email).set({
        "token_json": creds.to_json(),
        "updated_at": firestore.SERVER_TIMESTAMP,
    })
    logger.info(f"Saved token for {user_email}")


def load_token(user_email: str, scopes: list):
    """
    Load a user's credentials from Firestore.
    Automatically refreshes if expired.
    Returns None if no token exists or refresh fails.
    """
    doc = _db().collection(COLLECTION).document(user_email).get()

    if not doc.exists:
        logger.warning(f"No token found for {user_email}")
        return None

    token_json = doc.to_dict().get("token_json")
    creds = Credentials.from_authorized_user_info(json.loads(token_json), scopes)

    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        try:
            logger.info(f"Refreshing token for {user_email}")
            creds.refresh(Request())
            save_token(user_email, creds)  # save refreshed token
            return creds
        except RefreshError:
            logger.warning(f"Token refresh failed for {user_email} — re-login required")
            return None

    return None
