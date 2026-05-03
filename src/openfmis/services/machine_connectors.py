"""OAuth machine-data connector framework.

Defines the abstract connector interface and concrete implementations
for the major precision ag platforms.  Each connector handles OAuth2
token exchange, data listing, and file download.  Token storage and
refresh are delegated to the CredentialStore.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import httpx

log = logging.getLogger(__name__)


class ConnectorPlatform(StrEnum):
    """Supported machine data platforms."""

    JOHN_DEERE = "john_deere"
    CNH = "cnh"
    AGCO = "agco"
    TRIMBLE = "trimble"
    CLIMATE_FIELDVIEW = "climate_fieldview"


@dataclass
class OAuthToken:
    """OAuth2 token with expiry."""

    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    token_type: str = "Bearer"
    scope: str | None = None

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(UTC) >= self.expires_at


@dataclass
class ConnectorConfig:
    """Configuration for a machine data connector."""

    platform: ConnectorPlatform
    client_id: str
    client_secret: str
    redirect_uri: str
    base_url: str
    auth_url: str
    token_url: str
    scopes: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class MachineFile:
    """A file available for download from a machine data platform."""

    file_id: str
    filename: str
    file_type: str  # "yield", "as_applied", "planting", "harvest", "other"
    created_at: datetime | None = None
    field_name: str | None = None
    field_id: str | None = None
    size_bytes: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectorResult:
    """Result of a connector operation."""

    success: bool
    files: list[MachineFile] = field(default_factory=list)
    data: bytes | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


class MachineDataConnector(ABC):
    """Abstract base for machine data platform connectors."""

    platform: ConnectorPlatform

    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config
        self._token: OAuthToken | None = None

    @abstractmethod
    def get_auth_url(self, state: str) -> str:
        """Generate the OAuth2 authorization URL for user redirect."""

    @abstractmethod
    async def exchange_code(self, code: str) -> OAuthToken:
        """Exchange an authorization code for access + refresh tokens."""

    @abstractmethod
    async def refresh_token(self, token: OAuthToken) -> OAuthToken:
        """Refresh an expired access token."""

    @abstractmethod
    async def list_files(
        self,
        token: OAuthToken,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> ConnectorResult:
        """List available machine data files."""

    @abstractmethod
    async def download_file(
        self,
        token: OAuthToken,
        file_id: str,
    ) -> ConnectorResult:
        """Download a machine data file by ID."""

    async def upload_prescription(
        self,
        token: OAuthToken,
        filename: str,
        content: bytes,
        content_type: str = "application/zip",
        metadata: dict[str, Any] | None = None,
    ) -> ConnectorResult:
        """Upload a prescription file to the platform.

        Default implementation returns not-supported. Override in
        connectors that support prescription push.
        """
        return ConnectorResult(
            success=False,
            error=f"{self.platform} does not support prescription upload",
        )

    async def _post_token(self, data: dict[str, str], timeout: float = 15.0) -> dict[str, Any]:
        """Helper: POST to token endpoint and return JSON."""
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                self.config.token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            return resp.json()


# ── John Deere Operations Center ────────────────────────────────────────


class JohnDeereConnector(MachineDataConnector):
    """John Deere Operations Center API connector.

    Uses the MyJohnDeere API (v3) with OAuth2 for access to field
    operations, boundaries, and machine data files.
    """

    platform = ConnectorPlatform.JOHN_DEERE

    def get_auth_url(self, state: str) -> str:
        params = {
            "client_id": self.config.client_id,
            "response_type": "code",
            "redirect_uri": self.config.redirect_uri,
            "scope": " ".join(self.config.scopes),
            "state": state,
        }
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.config.auth_url}?{qs}"

    async def exchange_code(self, code: str) -> OAuthToken:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.config.redirect_uri,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }
        resp = await self._post_token(data)
        return _parse_token_response(resp)

    async def refresh_token(self, token: OAuthToken) -> OAuthToken:
        if not token.refresh_token:
            raise ValueError("No refresh token available")
        data = {
            "grant_type": "refresh_token",
            "refresh_token": token.refresh_token,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }
        resp = await self._post_token(data)
        return _parse_token_response(resp)

    async def list_files(
        self,
        token: OAuthToken,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> ConnectorResult:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                headers = {"Authorization": f"Bearer {token.access_token}"}
                # JD API: GET /platform/organizations/{org}/files
                resp = await client.get(
                    f"{self.config.base_url}/platform/files",
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()

            files = []
            for item in data.get("values", []):
                files.append(
                    MachineFile(
                        file_id=item.get("id", ""),
                        filename=item.get("name", ""),
                        file_type=_classify_jd_file(item),
                        created_at=_parse_iso(item.get("createdTime")),
                        metadata=item,
                    )
                )
            return ConnectorResult(success=True, files=files)
        except Exception as exc:
            return ConnectorResult(success=False, error=str(exc))

    async def download_file(self, token: OAuthToken, file_id: str) -> ConnectorResult:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                headers = {"Authorization": f"Bearer {token.access_token}"}
                resp = await client.get(
                    f"{self.config.base_url}/platform/files/{file_id}",
                    headers=headers,
                )
                resp.raise_for_status()
            return ConnectorResult(success=True, data=resp.content)
        except Exception as exc:
            return ConnectorResult(success=False, error=str(exc))

    async def upload_prescription(
        self,
        token: OAuthToken,
        filename: str,
        content: bytes,
        content_type: str = "application/zip",
        metadata: dict[str, Any] | None = None,
    ) -> ConnectorResult:
        """Push a prescription to JD Operations Center."""
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                headers = {
                    "Authorization": f"Bearer {token.access_token}",
                    "Content-Type": content_type,
                    "X-Deere-Filename": filename,
                }
                if metadata:
                    for k, v in metadata.items():
                        headers[f"X-Deere-{k}"] = str(v)
                resp = await client.post(
                    f"{self.config.base_url}/platform/files",
                    headers=headers,
                    content=content,
                )
                resp.raise_for_status()
            file_id = resp.headers.get("Location", "").rsplit("/", 1)[-1]
            return ConnectorResult(
                success=True,
                data={"file_id": file_id, "status": "uploaded"},
            )
        except Exception as exc:
            return ConnectorResult(success=False, error=str(exc))


# ── CNH AFS Connect ────────────────────────────────────────────────────


class CNHConnector(MachineDataConnector):
    """CNH Industrial AFS Connect API connector."""

    platform = ConnectorPlatform.CNH

    def get_auth_url(self, state: str) -> str:
        params = {
            "client_id": self.config.client_id,
            "response_type": "code",
            "redirect_uri": self.config.redirect_uri,
            "scope": " ".join(self.config.scopes),
            "state": state,
        }
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.config.auth_url}?{qs}"

    async def exchange_code(self, code: str) -> OAuthToken:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.config.redirect_uri,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }
        resp = await self._post_token(data)
        return _parse_token_response(resp)

    async def refresh_token(self, token: OAuthToken) -> OAuthToken:
        if not token.refresh_token:
            raise ValueError("No refresh token available")
        data = {
            "grant_type": "refresh_token",
            "refresh_token": token.refresh_token,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }
        resp = await self._post_token(data)
        return _parse_token_response(resp)

    async def list_files(
        self,
        token: OAuthToken,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> ConnectorResult:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                headers = {"Authorization": f"Bearer {token.access_token}"}
                resp = await client.get(
                    f"{self.config.base_url}/files",
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()

            files = []
            for item in data.get("files", []):
                files.append(
                    MachineFile(
                        file_id=item.get("id", ""),
                        filename=item.get("fileName", ""),
                        file_type=item.get("type", "other"),
                        metadata=item,
                    )
                )
            return ConnectorResult(success=True, files=files)
        except Exception as exc:
            return ConnectorResult(success=False, error=str(exc))

    async def download_file(self, token: OAuthToken, file_id: str) -> ConnectorResult:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                headers = {"Authorization": f"Bearer {token.access_token}"}
                resp = await client.get(
                    f"{self.config.base_url}/files/{file_id}/download",
                    headers=headers,
                )
                resp.raise_for_status()
            return ConnectorResult(success=True, data=resp.content)
        except Exception as exc:
            return ConnectorResult(success=False, error=str(exc))

    async def upload_prescription(
        self,
        token: OAuthToken,
        filename: str,
        content: bytes,
        content_type: str = "application/zip",
        metadata: dict[str, Any] | None = None,
    ) -> ConnectorResult:
        """Push a prescription to CNH AFS Connect."""
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                headers = {
                    "Authorization": f"Bearer {token.access_token}",
                }
                files_payload = {
                    "file": (filename, content, content_type),
                }
                resp = await client.post(
                    f"{self.config.base_url}/prescriptions/upload",
                    headers=headers,
                    files=files_payload,
                )
                resp.raise_for_status()
            result_data = (
                resp.json()
                if resp.headers.get("content-type", "").startswith("application/json")
                else {}
            )
            return ConnectorResult(
                success=True,
                data=result_data,
            )
        except Exception as exc:
            return ConnectorResult(success=False, error=str(exc))


# ── Connector Registry ─────────────────────────────────────────────────

CONNECTOR_CLASSES: dict[ConnectorPlatform, type[MachineDataConnector]] = {
    ConnectorPlatform.JOHN_DEERE: JohnDeereConnector,
    ConnectorPlatform.CNH: CNHConnector,
}


def create_connector(config: ConnectorConfig) -> MachineDataConnector:
    """Factory: create a connector instance for the given platform."""
    cls = CONNECTOR_CLASSES.get(config.platform)
    if cls is None:
        raise ValueError(
            f"No connector for platform '{config.platform}'. "
            f"Available: {', '.join(CONNECTOR_CLASSES)}"
        )
    return cls(config)


# ── Default configs ────────────────────────────────────────────────────


def default_config(
    platform: ConnectorPlatform,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> ConnectorConfig:
    """Create a ConnectorConfig with platform-specific defaults."""
    defaults: dict[ConnectorPlatform, dict[str, Any]] = {
        ConnectorPlatform.JOHN_DEERE: {
            "base_url": "https://sandboxapi.deere.com",
            "auth_url": "https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/authorize",
            "token_url": "https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/token",
            "scopes": ["ag1", "ag2", "ag3"],
        },
        ConnectorPlatform.CNH: {
            "base_url": "https://api.cnhindustrial.com/v1",
            "auth_url": "https://login.cnhindustrial.com/oauth2/authorize",
            "token_url": "https://login.cnhindustrial.com/oauth2/token",
            "scopes": ["field_operations"],
        },
        ConnectorPlatform.AGCO: {
            "base_url": "https://api.agco.com/v1",
            "auth_url": "https://accounts.agco.com/oauth2/authorize",
            "token_url": "https://accounts.agco.com/oauth2/token",
            "scopes": ["fuse"],
        },
        ConnectorPlatform.TRIMBLE: {
            "base_url": "https://cloud.trimble.com/api/v1",
            "auth_url": "https://id.trimble.com/oauth/authorize",
            "token_url": "https://id.trimble.com/oauth/token",
            "scopes": ["agriculture"],
        },
        ConnectorPlatform.CLIMATE_FIELDVIEW: {
            "base_url": "https://platform.climate.com/v4",
            "auth_url": "https://climate.com/static/app-login/index.html",
            "token_url": "https://api.climate.com/api/oauth/token",
            "scopes": ["fields:read", "prescriptions:write"],
        },
    }

    d = defaults.get(platform, {})
    return ConnectorConfig(
        platform=platform,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        base_url=d.get("base_url", ""),
        auth_url=d.get("auth_url", ""),
        token_url=d.get("token_url", ""),
        scopes=d.get("scopes", []),
    )


# ── Helpers ─────────────────────────────────────────────────────────────


def _parse_token_response(data: dict[str, Any]) -> OAuthToken:
    expires_in = data.get("expires_in")
    expires_at = None
    if expires_in:
        from datetime import timedelta

        expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))

    return OAuthToken(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token"),
        expires_at=expires_at,
        token_type=data.get("token_type", "Bearer"),
        scope=data.get("scope"),
    )


def _classify_jd_file(item: dict[str, Any]) -> str:
    """Classify a John Deere file by type."""
    name = (item.get("name", "") or "").lower()
    if "harvest" in name or "yield" in name:
        return "yield"
    elif "application" in name or "spray" in name:
        return "as_applied"
    elif "plant" in name or "seed" in name:
        return "planting"
    return "other"


def _parse_iso(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
