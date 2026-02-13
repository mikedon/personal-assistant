"""OAuth 2.0 manager for Granola MCP server authentication."""

import json
import logging
import os
import webbrowser
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

logger = logging.getLogger(__name__)


class GranolaOAuthManager:
    """Manages OAuth 2.0 authentication for Granola MCP server.

    Implements browser-based OAuth flow following the pattern established
    by GoogleOAuthManager, but adapted for Granola's MCP server.
    """

    # OAuth configuration for Granola MCP
    MCP_SERVER_URL = "https://mcp.granola.ai/mcp"
    OAUTH_AUTHORIZE_URL = "https://mcp.granola.ai/oauth/authorize"
    OAUTH_TOKEN_URL = "https://mcp.granola.ai/oauth/token"
    REDIRECT_URI = "http://localhost:8765/callback"
    SCOPES = ["meetings:read"]

    def __init__(self, token_path: Path):
        """Initialize Granola OAuth manager.

        Args:
            token_path: Path to store/load OAuth token file
        """
        self.token_path = Path(token_path)
        self._token_data: dict | None = None

    async def authenticate(self) -> str:
        """Run browser OAuth flow and return access token.

        Opens browser for user authorization, runs local callback server,
        exchanges authorization code for access token, and saves token.

        Returns:
            Access token for MCP API calls

        Raises:
            RuntimeError: If OAuth flow fails
        """
        try:
            logger.info("Starting Granola OAuth authentication flow")

            # Reset class variable before starting
            OAuthCallbackServer.auth_code = None

            # Start local callback server
            server_port = 8765
            server = HTTPServer(("localhost", server_port), OAuthCallbackServer)
            logger.debug(f"Started local OAuth callback server on port {server_port}")

            # Build authorization URL
            auth_url = (
                f"{self.OAUTH_AUTHORIZE_URL}"
                f"?response_type=code"
                f"&redirect_uri={self.REDIRECT_URI}"
                f"&scope={'+'.join(self.SCOPES)}"
            )

            # Open browser for authorization
            logger.info("Opening browser for Granola authorization...")
            webbrowser.open(auth_url)

            # Wait for callback (single request)
            server.handle_request()

            # Get authorization code from callback (class variable)
            if not OAuthCallbackServer.auth_code:
                raise RuntimeError(
                    "OAuth authorization failed: No authorization code received"
                )

            auth_code = OAuthCallbackServer.auth_code
            logger.debug("Received authorization code")

            # Exchange code for token
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.OAUTH_TOKEN_URL,
                    data={
                        "grant_type": "authorization_code",
                        "code": auth_code,
                        "redirect_uri": self.REDIRECT_URI,
                    },
                    headers={"Accept": "application/json"},
                )

                if response.status_code != 200:
                    raise RuntimeError(
                        f"Token exchange failed: {response.status_code} {response.text}"
                    )

                token_data = response.json()

            # Save token with secure permissions
            self._save_token(token_data)

            logger.info("Successfully authenticated with Granola MCP server")
            return token_data["access_token"]

        except Exception as e:
            logger.error(f"OAuth authentication failed: {e}")
            raise RuntimeError(f"Failed to authenticate with Granola: {e}") from e

    async def get_valid_token(self) -> str:
        """Get current access token, refreshing if needed.

        Returns:
            Valid access token

        Raises:
            RuntimeError: If token is missing or refresh fails
        """
        # Load token if not already in memory
        if not self._token_data:
            if not self.token_path.exists():
                raise RuntimeError(
                    f"No Granola OAuth token found at {self.token_path}. "
                    "Run 'pa accounts authenticate granola <workspace_id>' first."
                )

            with open(self.token_path) as f:
                self._token_data = json.load(f)

        # Check if token is expired
        expires_at = self._token_data.get("expires_at")
        if expires_at:
            expiry_time = datetime.fromisoformat(expires_at)
            now = datetime.now(UTC)

            # Refresh if expired or expiring soon (within 5 minutes)
            if now >= expiry_time - timedelta(minutes=5):
                logger.debug("Token expired or expiring soon, refreshing...")
                await self._refresh_token()

        return self._token_data["access_token"]

    async def _refresh_token(self) -> None:
        """Refresh expired access token using refresh token.

        Raises:
            RuntimeError: If refresh fails
        """
        if not self._token_data or "refresh_token" not in self._token_data:
            raise RuntimeError(
                "Cannot refresh token: No refresh token available. "
                "Please re-authenticate with 'pa accounts authenticate granola <workspace_id>'"
            )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.OAUTH_TOKEN_URL,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": self._token_data["refresh_token"],
                    },
                    headers={"Accept": "application/json"},
                )

                if response.status_code != 200:
                    raise RuntimeError(
                        f"Token refresh failed: {response.status_code} {response.text}"
                    )

                new_token_data = response.json()

            # Preserve refresh token if not included in response
            if "refresh_token" not in new_token_data:
                new_token_data["refresh_token"] = self._token_data["refresh_token"]

            # Save refreshed token
            self._save_token(new_token_data)
            logger.debug("Successfully refreshed Granola OAuth token")

        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            raise RuntimeError(f"Failed to refresh Granola token: {e}") from e

    def _save_token(self, token_data: dict) -> None:
        """Atomically save token with restricted permissions.

        Follows GoogleOAuthManager pattern for secure token storage:
        - Creates parent directory with 0o700 permissions
        - Atomically creates file with 0o600 permissions
        - Adds expiry timestamp for refresh logic

        Args:
            token_data: Token response from OAuth server

        Raises:
            IOError: If unable to save token file
        """
        try:
            # Add expiry timestamp if not present
            if "expires_in" in token_data and "expires_at" not in token_data:
                expires_at = datetime.now(UTC) + timedelta(seconds=token_data["expires_in"])
                token_data["expires_at"] = expires_at.isoformat()

            # Store in memory
            self._token_data = token_data

            # Create parent directory with restricted permissions (700)
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(self.token_path.parent, 0o700)

            # Atomically create file with secure permissions (600)
            # This prevents race condition where file could be world-readable
            fd = os.open(
                self.token_path,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                0o600
            )
            try:
                with os.fdopen(fd, 'w') as token_file:
                    json.dump(token_data, token_file, indent=2)
            except:
                os.close(fd)  # Clean up fd if fdopen fails
                raise

            logger.debug(f"Saved Granola OAuth token to {self.token_path}")

        except PermissionError as e:
            raise IOError(
                f"Permission denied saving OAuth token to {self.token_path}. "
                f"Ensure the directory is writable: {self.token_path.parent}"
            ) from e
        except OSError as e:
            raise IOError(
                f"Failed to save OAuth token to {self.token_path}. "
                f"Check disk space and permissions. Error: {e}"
            ) from e

    def is_authenticated(self) -> bool:
        """Check if we have a valid OAuth token.

        Returns:
            True if token file exists
        """
        return self.token_path.exists()

    def revoke(self) -> None:
        """Revoke credentials and remove token file."""
        if self.token_path.exists():
            self.token_path.unlink()
        self._token_data = None
        logger.info("Revoked Granola OAuth token")


class OAuthCallbackServer(BaseHTTPRequestHandler):
    """HTTP server handler for OAuth callback.

    Captures authorization code from OAuth redirect and displays
    success message to user.
    """

    auth_code: str | None = None

    def do_GET(self) -> None:
        """Handle OAuth callback GET request."""
        # Parse query parameters
        query_components = parse_qs(urlparse(self.path).query)

        if "code" in query_components:
            # Store authorization code (class variable shared across instances)
            OAuthCallbackServer.auth_code = query_components["code"][0]

            # Send success response
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body>"
                b"<h1>Authentication Successful!</h1>"
                b"<p>You can close this window and return to the terminal.</p>"
                b"</body></html>"
            )
        else:
            # Send error response
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            error = query_components.get("error", ["Unknown error"])[0]
            self.wfile.write(
                f"<html><body><h1>Authentication Failed</h1><p>Error: {error}</p></body></html>".encode()
            )

    def log_message(self, format: str, *args) -> None:
        """Suppress request logging."""
        pass
