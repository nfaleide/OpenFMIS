"""FastAPI dependencies — JWT extraction, current user resolution, permission checks."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.exceptions import AuthenticationError, AuthorizationError
from openfmis.models.user import User
from openfmis.security.jwt import decode_access_token

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Extract JWT, validate, and return the active User or raise 401."""
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise AuthenticationError("Invalid or expired token")

    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise AuthenticationError("Token missing subject")

    result = await db.execute(
        select(User).where(
            User.id == UUID(user_id),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise AuthenticationError("User not found or inactive")

    return user


def require_permission(
    permission: str,
    resource_type: str,
    resource_id: UUID | None = None,
) -> Callable:
    """FastAPI dependency factory — checks a permission before allowing access.

    Usage:
        @router.get("/fields", dependencies=[Depends(require_permission("fields.read", "fields"))])
    """

    async def _check(
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> None:
        from openfmis.services.acl import ACLService

        acl = ACLService(db)
        allowed = await acl.check_permission(user, permission, resource_type, resource_id)
        if not allowed:
            raise AuthorizationError(f"Permission '{permission}' denied on '{resource_type}'")

    return _check


async def get_superuser(
    user: Annotated["User", Depends(get_current_user)],
) -> "User":
    """Dependency that returns the current user only if they are a superuser."""
    if not user.is_superuser:
        raise AuthorizationError("Superuser access required")
    return user


def require_superuser() -> Callable:
    """Dependency that requires the current user to be a superuser."""

    async def _check(
        user: Annotated[User, Depends(get_current_user)],
    ) -> None:
        if not user.is_superuser:
            raise AuthorizationError("Superuser access required")

    return _check
