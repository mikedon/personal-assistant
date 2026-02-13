"""OAuth 2.1 manager for Granola MCP server authentication.

Implements MCP-compliant OAuth flow with:
- Authorization server discovery (RFC 9728)
- PKCE (Proof Key for Code Exchange) - required by MCP spec
- Resource indicators (RFC 8807)
"""

import base64
import hashlib
import json
import logging
import os
import secrets
import webbrowser
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

logger = logging.getLogger(__name__)


class GranolaOAuthManager:
    """Manages OAuth 2.1 authentication for Granola MCP server.

    Implements MCP-compliant browser-based OAuth flow with:
    - Authorization server discovery via RFC 9728
    - PKCE (required by MCP specification)
    - Resource indicators for token requests
    """

    # MCP server configuration
    MCP_SERVER_URL = "https://mcp.granola.ai/mcp"
    WELL_KNOWN_URL = "https://mcp.granola.ai/.well-known/oauth-authorization-server"
    REDIRECT_URI = "http://localhost:8765/callback"
    SCOPES = ["meetings:read"]

    # OAuth endpoints (discovered dynamically)
    _oauth_metadata: dict | None = None
    _client_id: str | None = None
    _client_secret: str | None = None  # Only used if confidential client

    def __init__(self, token_path: Path):
        """Initialize Granola OAuth manager.

        Args:
            token_path: Path to store/load OAuth token file
        """
        self.token_path = Path(token_path)
        self._token_data: dict | None = None

    async def _discover_oauth_metadata(self) -> dict:
        """Discover OAuth endpoints via RFC 9728.

        Returns:
            OAuth metadata dict with endpoints

        Raises:
            RuntimeError: If discovery fails
        """
        if self._oauth_metadata:
            return self._oauth_metadata

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.WELL_KNOWN_URL, timeout=10.0)
                response.raise_for_status()
                self._oauth_metadata = response.json()

                # Validate required fields
                required = ["authorization_endpoint", "token_endpoint"]
                for field in required:
                    if field not in self._oauth_metadata:
                        raise RuntimeError(f"OAuth metadata missing required field: {field}")

                logger.debug(f"Discovered OAuth endpoints: {self._oauth_metadata}")
                return self._oauth_metadata

        except httpx.HTTPError as e:
            raise RuntimeError(
                f"Failed to discover OAuth endpoints at {self.WELL_KNOWN_URL}: {e}"
            ) from e

    def _generate_pkce_pair(self) -> tuple[str, str]:
        """Generate PKCE code verifier and challenge.

        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        # Generate random code verifier (43-128 chars)
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')

        # Generate code challenge (SHA256 hash of verifier)
        challenge_bytes = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode('utf-8').rstrip('=')

        return code_verifier, code_challenge

    async def _register_client(self, metadata: dict) -> tuple[str, str | None]:
        """Register as OAuth client using Dynamic Client Registration (RFC 7591).

        Args:
            metadata: OAuth server metadata

        Returns:
            Tuple of (client_id, client_secret or None)

        Raises:
            RuntimeError: If registration fails or not supported
        """
        if not metadata.get("registration_endpoint"):
            # No DCR support - try without client_id (some MCP servers allow this)
            logger.warning(
                "OAuth server doesn't support Dynamic Client Registration. "
                "Attempting authentication without client_id."
            )
            return ("", None)

        try:
            registration_endpoint = metadata["registration_endpoint"]

            # Client metadata for registration
            client_metadata = {
                "client_name": "Personal Assistant CLI",
                "redirect_uris": [self.REDIRECT_URI],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",  # Public client (PKCE)
                "scope": " ".join(self.SCOPES),
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    registration_endpoint,
                    json=client_metadata,
                    headers={"Content-Type": "application/json"},
                    timeout=10.0,
                )

                if response.status_code == 201:
                    registration = response.json()
                    client_id = registration["client_id"]
                    client_secret = registration.get("client_secret")  # May be None for public clients

                    logger.info(f"Successfully registered OAuth client: {client_id}")
                    return (client_id, client_secret)
                else:
                    raise RuntimeError(
                        f"Client registration failed: {response.status_code} {response.text}"
                    )

        except httpx.HTTPError as e:
            raise RuntimeError(f"Failed to register OAuth client: {e}") from e

    async def authenticate(self) -> str:
        """Run MCP-compliant browser OAuth flow with PKCE.

        Implements:
        - Authorization server discovery (RFC 9728)
        - Dynamic Client Registration (RFC 7591)
        - PKCE (required by MCP spec)
        - Resource indicators (RFC 8807)

        Returns:
            Access token for MCP API calls

        Raises:
            RuntimeError: If OAuth flow fails
        """
        try:
            logger.info("Starting MCP-compliant OAuth authentication flow")

            # Discover OAuth endpoints
            metadata = await self._discover_oauth_metadata()
            auth_endpoint = metadata["authorization_endpoint"]
            token_endpoint = metadata["token_endpoint"]

            # Register as OAuth client (Dynamic Client Registration)
            self._client_id, self._client_secret = await self._register_client(metadata)

            # Generate PKCE pair
            code_verifier, code_challenge = self._generate_pkce_pair()

            # Reset class variable before starting
            OAuthCallbackServer.auth_code = None

            # Start local callback server
            server_port = 8765
            server = HTTPServer(("localhost", server_port), OAuthCallbackServer)
            logger.debug(f"Started local OAuth callback server on port {server_port}")

            # Build authorization URL with PKCE and client_id
            auth_params = {
                "response_type": "code",
                "redirect_uri": self.REDIRECT_URI,
                "scope": " ".join(self.SCOPES),
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }

            # Add client_id if we have one from registration
            if self._client_id:
                auth_params["client_id"] = self._client_id

            auth_url = f"{auth_endpoint}?{urlencode(auth_params)}"

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

            # Exchange code for token with PKCE verifier and resource indicator
            async with httpx.AsyncClient() as client:
                token_data = {
                    "grant_type": "authorization_code",
                    "code": auth_code,
                    "redirect_uri": self.REDIRECT_URI,
                    "code_verifier": code_verifier,
                    "resource": self.MCP_SERVER_URL,  # RFC 8807 resource indicator
                }

                # Add client credentials if we have them
                if self._client_id:
                    token_data["client_id"] = self._client_id
                if self._client_secret:
                    token_data["client_secret"] = self._client_secret

                response = await client.post(
                    token_endpoint,
                    data=token_data,
                    headers={"Accept": "application/json"},
                )

                if response.status_code != 200:
                    raise RuntimeError(
                        f"Token exchange failed: {response.status_code} {response.text}"
                    )

                token_response = response.json()

            # Save token with secure permissions
            self._save_token(token_response)

            logger.info("Successfully authenticated with Granola MCP server (OAuth 2.1 + PKCE + DCR)")
            return token_response["access_token"]

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

        Uses resource indicator as required by MCP spec.

        Raises:
            RuntimeError: If refresh fails
        """
        if not self._token_data or "refresh_token" not in self._token_data:
            raise RuntimeError(
                "Cannot refresh token: No refresh token available. "
                "Please re-authenticate with 'pa accounts authenticate granola <workspace_id>'"
            )

        try:
            # Discover token endpoint
            metadata = await self._discover_oauth_metadata()
            token_endpoint = metadata["token_endpoint"]

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    token_endpoint,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": self._token_data["refresh_token"],
                        "resource": self.MCP_SERVER_URL,  # RFC 8807 resource indicator
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
