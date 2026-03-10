"""ACLService — tri-state permission resolution with user > group precedence.

Resolution order:
1. Superusers always get GRANT on everything.
2. User-level privileges override group-level.
3. Group privileges are inherited up the group hierarchy (child → parent).
4. DENY at any level blocks access.
5. GRANT explicitly grants.
6. ALLOW defers to the next level (group → parent group → default deny).

For resource-level checks, we look for:
  - Exact resource match (resource_type + resource_id)
  - Wildcard match (resource_type + resource_id=NULL → applies to all)
User-level always takes precedence over group-level.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import NotFoundError
from openfmis.models.privilege import (
    GroupPrivilege,
    PermissionState,
    UserPrivilege,
)
from openfmis.models.user import User
from openfmis.schemas.privilege import PrivilegeGrant
from openfmis.services.group import GroupService


class ACLService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Permission checking ────────────────────────────────────────

    async def check_permission(
        self,
        user: User,
        permission: str,
        resource_type: str,
        resource_id: UUID | None = None,
    ) -> bool:
        """Check if a user has a specific permission. Returns True/False."""
        if user.is_superuser:
            return True

        effective = await self.get_effective_state(user, permission, resource_type, resource_id)
        return effective == PermissionState.GRANT

    async def get_effective_state(
        self,
        user: User,
        permission: str,
        resource_type: str,
        resource_id: UUID | None = None,
    ) -> PermissionState:
        """Resolve the effective state for a single permission.

        Returns GRANT, ALLOW, or DENY.
        """
        # 1. Check user-level privileges
        user_state = await self._get_user_permission(
            user.id, permission, resource_type, resource_id
        )
        if user_state in (PermissionState.GRANT, PermissionState.DENY):
            return user_state

        # 2. Check group-level privileges (walk up hierarchy)
        if user.group_id is not None:
            group_state = await self._get_group_permission_chain(
                user.group_id, permission, resource_type, resource_id
            )
            if group_state in (PermissionState.GRANT, PermissionState.DENY):
                return group_state

        # 3. Default: DENY
        return PermissionState.DENY

    async def get_effective_permissions(
        self,
        user: User,
        resource_type: str,
        resource_id: UUID | None = None,
    ) -> dict[str, str]:
        """Get all effective permissions for a user on a resource type.

        Returns a dict of {permission_name: effective_state}.
        """
        if user.is_superuser:
            # Collect all known permission names from both tables
            all_perms = await self._collect_all_permission_names(resource_type, resource_id)
            return {p: PermissionState.GRANT for p in all_perms}

        # Collect group permissions (bottom-up)
        group_perms: dict[str, str] = {}
        if user.group_id is not None:
            group_perms = await self._collect_group_permissions(
                user.group_id, resource_type, resource_id
            )

        # Collect user permissions (override group)
        user_perms = await self._collect_user_permissions(user.id, resource_type, resource_id)

        # Merge: user overrides group
        merged = {**group_perms, **user_perms}
        return merged

    # ── Privilege CRUD ─────────────────────────────────────────────

    async def grant_user_privilege(self, user_id: UUID, data: PrivilegeGrant) -> UserPrivilege:
        """Create or update a user privilege entry."""
        # Validate permission states
        self._validate_permission_states(data.permissions)

        existing = await self._find_user_privilege(user_id, data.resource_type, data.resource_id)
        if existing is not None:
            existing.permissions = {**existing.permissions, **data.permissions}
            await self.db.flush()
            await self.db.refresh(existing)
            return existing

        priv = UserPrivilege(
            user_id=user_id,
            resource_type=data.resource_type,
            resource_id=data.resource_id,
            permissions=data.permissions,
        )
        self.db.add(priv)
        await self.db.flush()
        return priv

    async def grant_group_privilege(self, group_id: UUID, data: PrivilegeGrant) -> GroupPrivilege:
        """Create or update a group privilege entry."""
        self._validate_permission_states(data.permissions)

        existing = await self._find_group_privilege(group_id, data.resource_type, data.resource_id)
        if existing is not None:
            existing.permissions = {**existing.permissions, **data.permissions}
            await self.db.flush()
            await self.db.refresh(existing)
            return existing

        priv = GroupPrivilege(
            group_id=group_id,
            resource_type=data.resource_type,
            resource_id=data.resource_id,
            permissions=data.permissions,
        )
        self.db.add(priv)
        await self.db.flush()
        return priv

    async def revoke_user_privilege(
        self, user_id: UUID, resource_type: str, resource_id: UUID | None = None
    ) -> None:
        priv = await self._find_user_privilege(user_id, resource_type, resource_id)
        if priv is not None:
            await self.db.delete(priv)
            await self.db.flush()

    async def revoke_group_privilege(
        self, group_id: UUID, resource_type: str, resource_id: UUID | None = None
    ) -> None:
        priv = await self._find_group_privilege(group_id, resource_type, resource_id)
        if priv is not None:
            await self.db.delete(priv)
            await self.db.flush()

    async def list_user_privileges(self, user_id: UUID) -> list[UserPrivilege]:
        result = await self.db.execute(
            select(UserPrivilege).where(UserPrivilege.user_id == user_id)
        )
        return list(result.scalars().all())

    async def list_group_privileges(self, group_id: UUID) -> list[GroupPrivilege]:
        result = await self.db.execute(
            select(GroupPrivilege).where(GroupPrivilege.group_id == group_id)
        )
        return list(result.scalars().all())

    # ── Internal helpers ───────────────────────────────────────────

    async def _get_user_permission(
        self,
        user_id: UUID,
        permission: str,
        resource_type: str,
        resource_id: UUID | None,
    ) -> PermissionState | None:
        """Look up a single permission from user_privileges."""
        # Try exact resource match first, then wildcard
        for rid in [resource_id, None] if resource_id else [None]:
            priv = await self._find_user_privilege(user_id, resource_type, rid)
            if priv is not None and permission in priv.permissions:
                return PermissionState(priv.permissions[permission])
        return None

    async def _get_group_permission_chain(
        self,
        group_id: UUID,
        permission: str,
        resource_type: str,
        resource_id: UUID | None,
    ) -> PermissionState | None:
        """Walk up the group hierarchy checking permissions at each level."""
        group_svc = GroupService(self.db)

        # Start with the user's direct group, then walk ancestors
        chain = [group_id]
        try:
            ancestors = await group_svc.get_ancestors(group_id)
            chain.extend(a.id for a in reversed(ancestors))  # child → root order
        except NotFoundError:
            pass

        for gid in chain:
            for rid in [resource_id, None] if resource_id else [None]:
                priv = await self._find_group_privilege(gid, resource_type, rid)
                if priv is not None and permission in priv.permissions:
                    state = PermissionState(priv.permissions[permission])
                    if state in (PermissionState.GRANT, PermissionState.DENY):
                        return state
                    # ALLOW means defer to parent
        return None

    async def _collect_user_permissions(
        self,
        user_id: UUID,
        resource_type: str,
        resource_id: UUID | None,
    ) -> dict[str, str]:
        """Collect all user-level permissions for a resource."""
        perms: dict[str, str] = {}
        # Wildcard first, then specific (specific overrides wildcard)
        for rid in [None, resource_id] if resource_id else [None]:
            priv = await self._find_user_privilege(user_id, resource_type, rid)
            if priv is not None:
                perms.update(priv.permissions)
        return perms

    async def _collect_group_permissions(
        self,
        group_id: UUID,
        resource_type: str,
        resource_id: UUID | None,
    ) -> dict[str, str]:
        """Collect group-level permissions walking up the hierarchy.

        Lower (closer to user) groups override higher groups.
        """
        group_svc = GroupService(self.db)
        chain = [group_id]
        try:
            ancestors = await group_svc.get_ancestors(group_id)
            chain.extend(a.id for a in reversed(ancestors))
        except NotFoundError:
            pass

        # Walk root → child so child overrides root
        perms: dict[str, str] = {}
        for gid in reversed(chain):
            for rid in [None, resource_id] if resource_id else [None]:
                priv = await self._find_group_privilege(gid, resource_type, rid)
                if priv is not None:
                    for perm_name, state in priv.permissions.items():
                        if state != PermissionState.ALLOW:
                            perms[perm_name] = state
                        elif perm_name not in perms:
                            perms[perm_name] = state
        return perms

    async def _collect_all_permission_names(
        self, resource_type: str, resource_id: UUID | None
    ) -> set[str]:
        """Get all distinct permission names for a resource type."""
        names: set[str] = set()
        for model in (UserPrivilege, GroupPrivilege):
            query = select(model.permissions).where(model.resource_type == resource_type)
            result = await self.db.execute(query)
            for (perms_dict,) in result.all():
                names.update(perms_dict.keys())
        return names

    async def _find_user_privilege(
        self, user_id: UUID, resource_type: str, resource_id: UUID | None
    ) -> UserPrivilege | None:
        query = select(UserPrivilege).where(
            UserPrivilege.user_id == user_id,
            UserPrivilege.resource_type == resource_type,
        )
        if resource_id is not None:
            query = query.where(UserPrivilege.resource_id == resource_id)
        else:
            query = query.where(UserPrivilege.resource_id.is_(None))

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _find_group_privilege(
        self, group_id: UUID, resource_type: str, resource_id: UUID | None
    ) -> GroupPrivilege | None:
        query = select(GroupPrivilege).where(
            GroupPrivilege.group_id == group_id,
            GroupPrivilege.resource_type == resource_type,
        )
        if resource_id is not None:
            query = query.where(GroupPrivilege.resource_id == resource_id)
        else:
            query = query.where(GroupPrivilege.resource_id.is_(None))

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    def _validate_permission_states(permissions: dict[str, str]) -> None:
        valid = {s.value for s in PermissionState}
        for name, state in permissions.items():
            if state not in valid:
                from openfmis.exceptions import ValidationError

                raise ValidationError(
                    f"Invalid permission state '{state}' for '{name}'. "
                    f"Must be one of: {', '.join(valid)}"
                )
