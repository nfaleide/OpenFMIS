"""API key service — create, verify, revoke, list."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import AuthenticationError, NotFoundError
from openfmis.models.api_key import APIKey


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


class APIKeyService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_key(
        self,
        user_id: UUID,
        name: str,
        *,
        expires_at: datetime | None = None,
        note: str | None = None,
    ) -> tuple[APIKey, str]:
        """Create a new API key. Returns (key_record, raw_key).

        The raw key is only available at creation time.
        """
        raw_key = secrets.token_hex(32)
        key_hash = _hash_key(raw_key)
        prefix = raw_key[:8]

        key = APIKey(
            user_id=user_id,
            name=name,
            key_hash=key_hash,
            key_prefix=prefix,
            expires_at=expires_at,
            note=note,
        )
        self.db.add(key)
        await self.db.flush()
        await self.db.refresh(key)
        return key, raw_key

    async def verify_key(self, raw_key: str) -> APIKey:
        """Verify an API key and return its record. Raises AuthenticationError on failure."""
        key_hash = _hash_key(raw_key)
        result = await self.db.execute(select(APIKey).where(APIKey.key_hash == key_hash))
        key = result.scalar_one_or_none()

        if key is None:
            raise AuthenticationError("Invalid API key")
        if key.revoked_at is not None:
            raise AuthenticationError("API key has been revoked")
        if key.expires_at is not None and key.expires_at < datetime.now(UTC):
            raise AuthenticationError("API key has expired")

        # Update last_used_at
        key.last_used_at = datetime.now(UTC)
        await self.db.flush()
        return key

    async def revoke_key(self, key_id: UUID, user_id: UUID) -> APIKey:
        """Revoke an API key. Only the owning user can revoke."""
        result = await self.db.execute(
            select(APIKey).where(APIKey.id == key_id, APIKey.user_id == user_id)
        )
        key = result.scalar_one_or_none()
        if key is None:
            raise NotFoundError("API key not found")
        if key.revoked_at is not None:
            raise NotFoundError("API key already revoked")

        key.revoked_at = datetime.now(UTC)
        await self.db.flush()
        await self.db.refresh(key)
        return key

    async def list_keys(self, user_id: UUID, include_revoked: bool = False) -> list[APIKey]:
        """List API keys for a user."""
        stmt = select(APIKey).where(APIKey.user_id == user_id).order_by(APIKey.created_at.desc())
        if not include_revoked:
            stmt = stmt.where(APIKey.revoked_at.is_(None))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_key(self, key_id: UUID, user_id: UUID) -> APIKey:
        """Get a specific API key by ID."""
        result = await self.db.execute(
            select(APIKey).where(APIKey.id == key_id, APIKey.user_id == user_id)
        )
        key = result.scalar_one_or_none()
        if key is None:
            raise NotFoundError("API key not found")
        return key
