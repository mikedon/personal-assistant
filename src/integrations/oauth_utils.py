"""OAuth 2.0 utilities for Google and Slack integrations."""

import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


class GoogleOAuthManager:
    """Manages OAuth 2.0 authentication for Google services."""

    def __init__(
        self,
        credentials_path: str | Path,
        token_path: str | Path,
        scopes: list[str],
    ):
        """Initialize OAuth manager.

        Args:
            credentials_path: Path to credentials.json from Google Cloud Console
            token_path: Path to store/load the token.json file
            scopes: List of OAuth scopes to request
        """
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self.scopes = scopes
        self._creds: Credentials | None = None

    def get_credentials(self) -> Credentials:
        """Get valid credentials, refreshing or re-authenticating if needed.

        Returns:
            Valid Google OAuth credentials.

        Raises:
            FileNotFoundError: If credentials.json doesn't exist
            ValueError: If authentication fails
        """
        # Load existing token if available
        if self.token_path.exists():
            self._creds = Credentials.from_authorized_user_file(
                str(self.token_path), self.scopes
            )

        # If no valid credentials, authenticate
        if not self._creds or not self._creds.valid:
            if self._creds and self._creds.expired and self._creds.refresh_token:
                # Refresh expired credentials
                self._creds.refresh(Request())
            else:
                # Run OAuth flow
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        f"Credentials file not found: {self.credentials_path}. "
                        "Download from Google Cloud Console."
                    )

                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), self.scopes
                )
                self._creds = flow.run_local_server(port=0)

            # Save credentials for next run
            self._save_credentials()

        return self._creds

    def _save_credentials(self) -> None:
        """Save credentials to token file with restricted permissions."""
        if self._creds:
            # Create parent directory with restricted permissions
            self.token_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

            # Write token file
            with open(self.token_path, "w") as token:
                token.write(self._creds.to_json())

            # Set restrictive permissions (owner read/write only)
            os.chmod(self.token_path, 0o600)

    def is_authenticated(self) -> bool:
        """Check if we have valid credentials.

        Returns:
            True if authenticated with valid credentials.
        """
        try:
            creds = self.get_credentials()
            return creds is not None and creds.valid
        except Exception:
            return False

    def revoke(self) -> None:
        """Revoke credentials and remove token file."""
        if self._creds and self._creds.valid:
            self._creds.revoke(Request())
        if self.token_path.exists():
            self.token_path.unlink()
        self._creds = None


class SlackOAuthManager:
    """Manages authentication for Slack API."""

    def __init__(self, bot_token: str, app_token: str | None = None):
        """Initialize Slack OAuth manager.

        Args:
            bot_token: Slack bot token (xoxb-...)
            app_token: Slack app token for socket mode (xapp-...)
        """
        self.bot_token = bot_token
        self.app_token = app_token

    def get_bot_token(self) -> str:
        """Get bot token for API calls.

        Returns:
            Slack bot token.

        Raises:
            ValueError: If token is not configured.
        """
        if not self.bot_token:
            raise ValueError("Slack bot token not configured")
        return self.bot_token

    def get_app_token(self) -> str:
        """Get app token for socket mode.

        Returns:
            Slack app token.

        Raises:
            ValueError: If token is not configured.
        """
        if not self.app_token:
            raise ValueError("Slack app token not configured")
        return self.app_token

    def is_authenticated(self) -> bool:
        """Check if we have valid tokens.

        Returns:
            True if bot token is configured.
        """
        return bool(self.bot_token)
