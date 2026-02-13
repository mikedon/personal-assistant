"""Unit tests for Granola OAuth manager."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from src.integrations.granola_oauth import GranolaOAuthManager


@pytest.fixture
def token_path(tmp_path):
    """Temporary token file path."""
    return tmp_path / "token.granola.json"


@pytest.fixture
def mock_token_data():
    """Sample OAuth token response."""
    expires_at = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    return {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "expires_at": expires_at,
    }


class TestGranolaOAuthManager:
    """Test Granola OAuth manager functionality."""

    def test_initialization(self, token_path):
        """Test OAuth manager initialization."""
        manager = GranolaOAuthManager(token_path)

        assert manager.token_path == token_path
        assert manager._token_data is None
        assert manager.MCP_SERVER_URL == "https://mcp.granola.ai/mcp"

    @pytest.mark.asyncio
    async def test_authenticate_success(self, token_path, mock_token_data):
        """Test successful MCP-compliant OAuth authentication flow with PKCE."""
        manager = GranolaOAuthManager(token_path)

        # Mock OAuth metadata discovery
        mock_metadata = {
            "authorization_endpoint": "https://mcp.granola.ai/oauth/authorize",
            "token_endpoint": "https://mcp.granola.ai/oauth/token",
        }

        # Mock browser opening
        with patch("webbrowser.open") as mock_browser:
            # Mock callback server and handler
            with patch("src.integrations.granola_oauth.HTTPServer") as mock_server_class:
                with patch("src.integrations.granola_oauth.OAuthCallbackServer") as mock_callback_class:
                    mock_server = MagicMock()
                    mock_server_class.return_value = mock_server

                    # Simulate auth code being set when handle_request() is called
                    def set_auth_code():
                        mock_callback_class.auth_code = "test_auth_code"

                    mock_server.handle_request.side_effect = set_auth_code

                    # Mock HTTP responses
                    with patch("httpx.AsyncClient") as mock_client_class:
                        mock_client = MagicMock()

                        # Mock discovery response
                        mock_discovery_response = MagicMock()
                        mock_discovery_response.json.return_value = mock_metadata
                        mock_discovery_response.raise_for_status = MagicMock()

                        # Mock token exchange response
                        mock_token_response = MagicMock()
                        mock_token_response.status_code = 200
                        mock_token_response.json.return_value = mock_token_data

                        # Setup client to return different responses
                        async def mock_request(url_or_method, *args, **kwargs):
                            if ".well-known" in str(url_or_method):
                                return mock_discovery_response
                            return mock_token_response

                        mock_client.get = AsyncMock(return_value=mock_discovery_response)
                        mock_client.post = AsyncMock(return_value=mock_token_response)
                        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                        mock_client.__aexit__ = AsyncMock()
                        mock_client_class.return_value = mock_client

                        # Run authentication
                        token = await manager.authenticate()

                        # Verify
                        assert token == "test_access_token"
                        mock_browser.assert_called_once()
                        assert token_path.exists()

                        # Verify PKCE parameters were used
                        call_args = mock_client.post.call_args
                        assert "code_verifier" in call_args.kwargs["data"]
                        assert "resource" in call_args.kwargs["data"]

    @pytest.mark.asyncio
    async def test_get_valid_token_from_file(self, token_path, mock_token_data):
        """Test getting valid token from saved file."""
        # Write token file
        with open(token_path, "w") as f:
            json.dump(mock_token_data, f)

        manager = GranolaOAuthManager(token_path)

        token = await manager.get_valid_token()

        assert token == "test_access_token"
        assert manager._token_data == mock_token_data

    @pytest.mark.asyncio
    async def test_get_valid_token_missing_file(self, token_path):
        """Test error when token file doesn't exist."""
        manager = GranolaOAuthManager(token_path)

        with pytest.raises(RuntimeError, match="No Granola OAuth token found"):
            await manager.get_valid_token()

    @pytest.mark.asyncio
    async def test_get_valid_token_refresh_when_expired(self, token_path):
        """Test automatic token refresh when expired."""
        # Create expired token
        expired_token_data = {
            "access_token": "old_access_token",
            "refresh_token": "test_refresh_token",
            "expires_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        }

        with open(token_path, "w") as f:
            json.dump(expired_token_data, f)

        manager = GranolaOAuthManager(token_path)

        # Mock OAuth metadata discovery
        mock_metadata = {
            "authorization_endpoint": "https://mcp.granola.ai/oauth/authorize",
            "token_endpoint": "https://mcp.granola.ai/oauth/token",
        }

        # Mock refresh response
        new_token_data = {
            "access_token": "new_access_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()

            # Mock discovery response
            mock_discovery_response = MagicMock()
            mock_discovery_response.json.return_value = mock_metadata
            mock_discovery_response.raise_for_status = MagicMock()

            # Mock token response
            mock_token_response = MagicMock()
            mock_token_response.status_code = 200
            mock_token_response.json.return_value = new_token_data

            mock_client.get = AsyncMock(return_value=mock_discovery_response)
            mock_client.post = AsyncMock(return_value=mock_token_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            token = await manager.get_valid_token()

            # Verify token was refreshed
            assert token == "new_access_token"
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, token_path):
        """Test successful token refresh with resource indicator."""
        manager = GranolaOAuthManager(token_path)
        manager._token_data = {
            "access_token": "old_token",
            "refresh_token": "test_refresh_token",
        }

        # Mock OAuth metadata discovery
        mock_metadata = {
            "authorization_endpoint": "https://mcp.granola.ai/oauth/authorize",
            "token_endpoint": "https://mcp.granola.ai/oauth/token",
        }

        # Mock refresh response
        new_token_data = {
            "access_token": "new_access_token",
            "expires_in": 3600,
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()

            # Mock discovery response
            mock_discovery_response = MagicMock()
            mock_discovery_response.json.return_value = mock_metadata
            mock_discovery_response.raise_for_status = MagicMock()

            # Mock token response
            mock_token_response = MagicMock()
            mock_token_response.status_code = 200
            mock_token_response.json.return_value = new_token_data

            mock_client.get = AsyncMock(return_value=mock_discovery_response)
            mock_client.post = AsyncMock(return_value=mock_token_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            await manager._refresh_token()

            # Verify refresh token preserved
            assert manager._token_data["refresh_token"] == "test_refresh_token"
            assert manager._token_data["access_token"] == "new_access_token"

            # Verify resource indicator was included
            call_args = mock_client.post.call_args
            assert "resource" in call_args.kwargs["data"]

    @pytest.mark.asyncio
    async def test_refresh_token_missing_refresh_token(self, token_path):
        """Test error when refresh token not available."""
        manager = GranolaOAuthManager(token_path)
        manager._token_data = {"access_token": "test_token"}  # No refresh_token

        with pytest.raises(RuntimeError, match="Cannot refresh token"):
            await manager._refresh_token()

    def test_save_token_creates_directory(self, token_path, mock_token_data):
        """Test token save creates parent directory with correct permissions."""
        manager = GranolaOAuthManager(token_path)

        manager._save_token(mock_token_data)

        assert token_path.exists()
        assert token_path.parent.exists()

        # Check file permissions (0o600 = owner read/write only)
        import stat
        file_stat = token_path.stat()
        assert stat.S_IMODE(file_stat.st_mode) == 0o600

    def test_save_token_adds_expiry_timestamp(self, token_path):
        """Test token save adds expiry timestamp."""
        manager = GranolaOAuthManager(token_path)

        token_data = {
            "access_token": "test_token",
            "expires_in": 3600,
        }

        manager._save_token(token_data)

        # Verify expires_at was added
        with open(token_path) as f:
            saved_data = json.load(f)

        assert "expires_at" in saved_data
        expires_at = datetime.fromisoformat(saved_data["expires_at"])
        now = datetime.now(UTC)
        assert expires_at > now
        assert expires_at < now + timedelta(hours=2)

    def test_is_authenticated(self, token_path, mock_token_data):
        """Test authentication check."""
        manager = GranolaOAuthManager(token_path)

        # Not authenticated initially
        assert not manager.is_authenticated()

        # Authenticated after saving token
        with open(token_path, "w") as f:
            json.dump(mock_token_data, f)

        assert manager.is_authenticated()

    def test_revoke_removes_token(self, token_path, mock_token_data):
        """Test token revocation."""
        manager = GranolaOAuthManager(token_path)

        # Create token file
        with open(token_path, "w") as f:
            json.dump(mock_token_data, f)

        manager._token_data = mock_token_data

        # Revoke
        manager.revoke()

        # Verify cleanup
        assert not token_path.exists()
        assert manager._token_data is None
