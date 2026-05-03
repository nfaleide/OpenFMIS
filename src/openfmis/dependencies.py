"""FastAPI dependencies — JWT extraction, current user resolution, permission checks."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.exceptions import AuthenticationError, AuthorizationError, NotFoundError
from openfmis.models.token_blacklist import TokenBlacklist
from openfmis.models.user import User
from openfmis.security.jwt import decode_access_token

bearer_scheme = HTTPBearer()


def _require_group(user: User) -> UUID:
    """Return the user's group_id or raise 403 if unset."""
    if user.group_id is None:
        raise AuthorizationError("User must belong to a group")
    return user.group_id


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Extract JWT, validate, and return the active User or raise 401."""
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise AuthenticationError("Invalid or expired token")

    # Check token blacklist (logout enforcement)
    jti: str | None = payload.get("jti")
    if jti is not None:
        bl_result = await db.execute(select(TokenBlacklist).where(TokenBlacklist.jti == jti))
        if bl_result.scalar_one_or_none() is not None:
            raise AuthenticationError("Token has been revoked")

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


async def verify_group_access(user: User, group_id: UUID) -> None:
    """Raise 403 if user doesn't belong to the given group (superusers pass)."""
    if user.is_superuser:
        return
    user_gid = _require_group(user)
    if user_gid != group_id:
        raise AuthorizationError("Access denied — resource belongs to another group")


async def verify_field_access(
    user: User,
    field_id: UUID,
    db: AsyncSession,
) -> None:
    """Verify user can access a field by checking field's group_id matches user's."""
    if user.is_superuser:
        return
    user_gid = _require_group(user)

    from openfmis.models.field import Field

    result = await db.execute(
        select(Field.group_id).where(Field.id == field_id, Field.deleted_at.is_(None))
    )
    field_group = result.scalar_one_or_none()
    if field_group is None:
        raise NotFoundError("Field not found")
    if field_group != user_gid:
        raise AuthorizationError("Access denied — field belongs to another group")


async def verify_entity_group_access(
    user: User,
    entity_id: UUID,
    model_class: type,
    db: AsyncSession,
    *,
    label: str = "Resource",
) -> None:
    """Generic check: load entity → look up its field → verify group ownership.

    Works for CropYear, PointDataset, Prescription, InterpolationSurface, etc.
    The model must have a ``field_id`` attribute.
    """
    if user.is_superuser:
        return
    user_gid = _require_group(user)

    from openfmis.models.field import Field

    result = await db.execute(select(model_class).where(model_class.id == entity_id))
    entity = result.scalar_one_or_none()
    if entity is None:
        raise NotFoundError(f"{label} not found")

    # Check soft-delete if the model supports it
    if hasattr(entity, "deleted_at") and entity.deleted_at is not None:
        raise NotFoundError(f"{label} not found")

    field_result = await db.execute(select(Field.group_id).where(Field.id == entity.field_id))
    field_group = field_result.scalar_one_or_none()
    if field_group is None or field_group != user_gid:
        raise AuthorizationError(f"Access denied — {label.lower()} belongs to another group")
