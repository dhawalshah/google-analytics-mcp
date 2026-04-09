"""
Google Analytics OAuth Authentication - multi-user server version.

Instead of reading a local token file, this reads each user's token
from Firestore using the currently logged-in user's email.
"""

import os
import contextvars
import logging
from typing import Dict

from .firestore_tokens import load_token

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/analytics",
    "https://www.googleapis.com/auth/analytics.readonly",
]

# This is set by the auth middleware in main.py for every request.
# It holds the email of the currently logged-in user.
current_user_email: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_user_email", default=None
)


def get_headers_with_auto_token() -> Dict[str, str]:
    """
    Get API headers using the current user's stored token.
    Raises an error if no user is logged in.
    """
    email = current_user_email.get()

    if not email:
        raise ValueError(
            "No authenticated user found. "
            "Please visit /auth/login to connect your Google account."
        )

    creds = load_token(email, SCOPES)

    if not creds:
        raise ValueError(
            f"No valid token for {email}. "
            "Please visit /auth/login to reconnect your Google account."
        )

    return {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
    }
