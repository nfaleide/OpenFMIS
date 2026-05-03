"""Plugin SDK — ACL delegation.

Plugins must never access the ACL tables directly. This module provides
a thin async wrapper around the core ACLService.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.user import User
from openfmis.services.acl import ACLService


async def check_permission(
    db: AsyncSession,
    user: User,
    permission: str,
    resource_type: str,
    resource_id: UUID | None = None,
) -> bool:
    """Check whether *user* holds *permission* on *resource_type*.

    Optionally scoped to *resource_id*. Returns True if allowed.
    """
    acl = ACLService(db)
    return await acl.check_permission(user, permission, resource_type, resource_id)
