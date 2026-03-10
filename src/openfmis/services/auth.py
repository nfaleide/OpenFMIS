"""AuthService — login, refresh, logout, token validation.

Handles the MD5→Argon2id lazy migration: when a user with a legacy
MD5 hash logs in successfully, their password is transparently
re-hashed to Argon2id.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import AuthenticationError
from openfmis.models.token_blacklist import TokenBlacklist
from openfmis.models.user import User
from openfmis.security.jwt import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from openfmis.security.password import hash_password, needs_rehash, verify_password


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def authenticate(self, username: str, password: str) -> tuple[str, str]:
        """Verify credentials and return (access_token, refresh_token).

        Raises AuthenticationError on failure.
        """
        result = await self.db.execute(
            select(User).where(
                User.username == username,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
        user = result.scalar_one_or_none()

        if user is None or not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid username or password")

        # Lazy migration: re-hash if MD5 or outdated Argon2 params
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
            await self.db.flush()

        access_token = create_access_token(user.id)
        refresh_token = create_refresh_token(user.id)
        return access_token, refresh_token

    async def refresh_tokens(self, refresh_token_str: str) -> tuple[str, str]:
        """Validate refresh token, check blacklist, issue new pair."""
        payload = decode_refresh_token(refresh_token_str)
        if payload is None:
            raise AuthenticationError("Invalid or expired refresh token")

        jti = payload.get("jti")
        if jti and await self._is_token_revoked(jti):
            raise AuthenticationError("Token has been revoked")

        user_id = payload["sub"]

        # Verify user still active
        result = await self.db.execute(
            select(User).where(
                User.id == UUID(user_id),
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise AuthenticationError("User not found or inactive")

        # Revoke old refresh token
        if jti:
            await self._revoke_token(jti, datetime.fromtimestamp(payload["exp"], tz=UTC))

        return create_access_token(user.id), create_refresh_token(user.id)

    async def logout(self, access_jti: str, access_exp: datetime) -> None:
        """Revoke the current access token."""
        await self._revoke_token(access_jti, access_exp)

    async def _is_token_revoked(self, jti: str) -> bool:
        result = await self.db.execute(select(TokenBlacklist).where(TokenBlacklist.jti == jti))
        return result.scalar_one_or_none() is not None

    async def _revoke_token(self, jti: str, expires_at: datetime) -> None:
        entry = TokenBlacklist(jti=jti, expires_at=expires_at)
        self.db.add(entry)
        await self.db.flush()
