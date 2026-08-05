"""
utils/google_auth.py
--------------------
Handles Google OAuth 2.0 credentials loading, refreshing, local flow, and client service creation.
"""

import os
from pathlib import Path
from typing import Any
from config import DATA_DIR
from utils.logger import get_logger

logger = get_logger(__name__)

# Essential scopes to interact with Gmail, Google Calendar, and Google Drive
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.readonly"
]


def get_google_service(service_name: str, version: str) -> Any:
    """
    Retrieves a cached Google API client service using OAuth 2.0.
    In testing environment (ENVIRONMENT=test), returns a MagicMock to allow headless runs.

    Args:
        service_name: Google API name (e.g., 'gmail', 'calendar', 'drive').
        version: API version (e.g., 'v1', 'v3').

    Returns:
        Built client service instance, or a MagicMock.
    """
    # Headless test run interception
    if os.getenv("ENVIRONMENT") == "test":
        from unittest.mock import MagicMock
        logger.info("[MockAuth] Stubbing Google API service client for %s:%s", service_name, version)
        return MagicMock()

    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    token_path = DATA_DIR / "token.json"
    creds_path = DATA_DIR / "credentials.json"

    # Load existing OAuth token
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            logger.debug("Successfully loaded existing Google token credentials.")
        except Exception as e:
            logger.warning("Failed to load existing credentials token: %s", e)

    # Refresh or run auth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logger.info("Refreshed Google OAuth credentials token.")
            except Exception as e:
                logger.warning("Failed to refresh Google credentials token: %s", e)
                creds = None

        if not creds:
            if not creds_path.exists():
                logger.error("credentials.json not found at %s", creds_path)
                raise FileNotFoundError(
                    f"Google API credentials file not found at '{creds_path}'. "
                    "Please download credentials.json from Google Cloud Console "
                    "and place it in the data directory to authenticate."
                )
            
            logger.info("Running local OAuth web server flow for first-time authentication...")
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)

        # Cache credentials token locally
        try:
            with open(token_path, "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())
            logger.info("Cached Google token credentials to %s.", token_path)
        except Exception as e:
            logger.error("Failed to cache Google token credentials: %s", e)

    return build(service_name, version, credentials=creds)
