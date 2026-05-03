"""Tests for machine data connector framework."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from openfmis.services.machine_connectors import (
    CNHConnector,
    ConnectorConfig,
    ConnectorPlatform,
    JohnDeereConnector,
    OAuthToken,
    _classify_jd_file,
    _parse_iso,
    _parse_token_response,
    create_connector,
    default_config,
)


def _jd_config() -> ConnectorConfig:
    return ConnectorConfig(
        platform=ConnectorPlatform.JOHN_DEERE,
        client_id="test_id",
        client_secret="test_secret",
        redirect_uri="http://localhost/callback",
        base_url="https://sandboxapi.deere.com",
        auth_url="https://signin.johndeere.com/oauth2/authorize",
        token_url="https://signin.johndeere.com/oauth2/token",
        scopes=["ag1", "ag2"],
    )


def _cnh_config() -> ConnectorConfig:
    return ConnectorConfig(
        platform=ConnectorPlatform.CNH,
        client_id="test_id",
        client_secret="test_secret",
        redirect_uri="http://localhost/callback",
        base_url="https://api.cnhindustrial.com/v1",
        auth_url="https://login.cnhindustrial.com/authorize",
        token_url="https://login.cnhindustrial.com/token",
        scopes=["field_operations"],
    )


class TestOAuthToken:
    def test_not_expired(self):
        token = OAuthToken(
            access_token="abc",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert not token.is_expired

    def test_expired(self):
        token = OAuthToken(
            access_token="abc",
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert token.is_expired

    def test_no_expiry(self):
        token = OAuthToken(access_token="abc")
        assert not token.is_expired


class TestTokenParsing:
    def test_parse_token_response(self):
        data = {
            "access_token": "at_123",
            "refresh_token": "rt_456",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "ag1 ag2",
        }
        token = _parse_token_response(data)
        assert token.access_token == "at_123"
        assert token.refresh_token == "rt_456"
        assert token.token_type == "Bearer"
        assert token.scope == "ag1 ag2"
        assert token.expires_at is not None
        assert not token.is_expired


class TestJohnDeere:
    def test_auth_url(self):
        conn = JohnDeereConnector(_jd_config())
        url = conn.get_auth_url("mystate")
        assert "client_id=test_id" in url
        assert "state=mystate" in url
        assert "response_type=code" in url

    @pytest.mark.asyncio
    async def test_exchange_code(self):
        conn = JohnDeereConnector(_jd_config())
        mock_resp = {
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 3600,
        }
        with patch.object(conn, "_post_token", new_callable=AsyncMock) as mock:
            mock.return_value = mock_resp
            token = await conn.exchange_code("authcode")
            assert token.access_token == "at"
            assert token.refresh_token == "rt"

    @pytest.mark.asyncio
    async def test_refresh_token(self):
        conn = JohnDeereConnector(_jd_config())
        old = OAuthToken(access_token="old", refresh_token="rt")
        mock_resp = {
            "access_token": "new_at",
            "refresh_token": "new_rt",
            "expires_in": 3600,
        }
        with patch.object(conn, "_post_token", new_callable=AsyncMock) as mock:
            mock.return_value = mock_resp
            token = await conn.refresh_token(old)
            assert token.access_token == "new_at"

    @pytest.mark.asyncio
    async def test_refresh_without_token_fails(self):
        conn = JohnDeereConnector(_jd_config())
        old = OAuthToken(access_token="old", refresh_token=None)
        with pytest.raises(ValueError, match="No refresh token"):
            await conn.refresh_token(old)


class TestCNH:
    def test_auth_url(self):
        conn = CNHConnector(_cnh_config())
        url = conn.get_auth_url("state123")
        assert "client_id=test_id" in url
        assert "state=state123" in url


class TestConnectorFactory:
    def test_create_jd(self):
        conn = create_connector(_jd_config())
        assert isinstance(conn, JohnDeereConnector)

    def test_create_cnh(self):
        conn = create_connector(_cnh_config())
        assert isinstance(conn, CNHConnector)

    def test_unknown_platform(self):
        config = ConnectorConfig(
            platform=ConnectorPlatform.AGCO,
            client_id="x",
            client_secret="x",
            redirect_uri="x",
            base_url="x",
            auth_url="x",
            token_url="x",
        )
        with pytest.raises(ValueError, match="No connector"):
            create_connector(config)


class TestDefaultConfig:
    def test_jd_defaults(self):
        cfg = default_config(
            ConnectorPlatform.JOHN_DEERE,
            "myid",
            "mysecret",
            "http://localhost/cb",
        )
        assert cfg.platform == ConnectorPlatform.JOHN_DEERE
        assert cfg.client_id == "myid"
        assert "deere.com" in cfg.base_url
        assert len(cfg.scopes) > 0

    def test_all_platforms_have_defaults(self):
        for platform in ConnectorPlatform:
            cfg = default_config(platform, "id", "secret", "http://cb")
            assert cfg.platform == platform


class TestHelpers:
    def test_classify_yield(self):
        assert _classify_jd_file({"name": "harvest_2024.zip"}) == "yield"

    def test_classify_applied(self):
        assert _classify_jd_file({"name": "spray_north40.zip"}) == "as_applied"

    def test_classify_planting(self):
        assert _classify_jd_file({"name": "planting_corn.zip"}) == "planting"

    def test_classify_other(self):
        assert _classify_jd_file({"name": "boundaries.zip"}) == "other"

    def test_parse_iso(self):
        dt = _parse_iso("2024-05-01T12:00:00Z")
        assert dt is not None
        assert dt.year == 2024

    def test_parse_iso_none(self):
        assert _parse_iso(None) is None
        assert _parse_iso("bogus") is None


# ── Prescription Upload ───────────────────────────────────────────────


class TestPrescriptionUpload:
    @pytest.mark.asyncio
    async def test_jd_upload_prescription(self):
        """JD connector upload sends POST with correct headers."""
        connector = JohnDeereConnector(_jd_config())
        token = OAuthToken(access_token="test-token")

        mock_resp = AsyncMock()
        mock_resp.status_code = 201
        mock_resp.raise_for_status = lambda: None
        mock_resp.headers = {"Location": "/platform/files/rx-123"}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await connector.upload_prescription(token, "rx_field.zip", b"fake-zip-content")
            assert result.success is True
            assert result.data["file_id"] == "rx-123"

    @pytest.mark.asyncio
    async def test_jd_upload_failure(self):
        """JD connector handles upload failure gracefully."""
        connector = JohnDeereConnector(_jd_config())
        token = OAuthToken(access_token="test-token")

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(side_effect=Exception("Network error"))
            mock_client_cls.return_value = mock_client

            result = await connector.upload_prescription(token, "rx.zip", b"data")
            assert result.success is False
            assert "Network error" in result.error

    @pytest.mark.asyncio
    async def test_base_class_upload_not_supported(self):
        """Connectors without upload return not-supported error."""
        from openfmis.services.machine_connectors import MachineDataConnector

        # Create a minimal concrete subclass that doesn't override upload
        class StubConnector(MachineDataConnector):
            platform = ConnectorPlatform.AGCO

            def get_auth_url(self, state):
                return ""

            async def exchange_code(self, code):
                pass

            async def refresh_token(self, token):
                pass

            async def list_files(self, token, **kw):
                pass

            async def download_file(self, token, file_id):
                pass

        config = _jd_config()
        config.platform = ConnectorPlatform.AGCO
        stub = StubConnector(config)
        token = OAuthToken(access_token="test")

        result = await stub.upload_prescription(token, "rx.zip", b"data")
        assert result.success is False
        assert "does not support" in result.error
