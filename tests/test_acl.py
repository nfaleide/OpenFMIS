"""ACL tests — tri-state resolution, hierarchy, admin guard, privilege ceiling."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import ValidationError
from openfmis.models.group import Group
from openfmis.models.user import User
from openfmis.schemas.privilege import PrivilegeGrant
from openfmis.security.password import hash_password
from openfmis.services.acl import ACLService

# ── Helpers ────────────────────────────────────────────────────


async def _login(
    client: AsyncClient, username: str = "testuser", password: str = "testpassword123"
) -> str:
    resp = await client.post("/api/v1/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── Unit tests via ACLService directly ─────────────────────────


@pytest.mark.asyncio
async def test_superuser_always_granted(db_session: AsyncSession):
    """Superusers bypass all permission checks."""
    user = User(
        id=uuid.uuid4(),
        username="superadmin",
        password_hash=hash_password("pw"),
        is_active=True,
        is_superuser=True,
    )
    db_session.add(user)
    await db_session.flush()

    acl = ACLService(db_session)
    assert await acl.check_permission(user, "anything.here", "any_resource") is True


@pytest.mark.asyncio
async def test_no_privileges_means_deny(db_session: AsyncSession):
    """A user with no privileges is denied by default."""
    user = User(
        id=uuid.uuid4(),
        username="noprivs",
        password_hash=hash_password("pw"),
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()

    acl = ACLService(db_session)
    assert await acl.check_permission(user, "fields.read", "fields") is False


@pytest.mark.asyncio
async def test_user_grant_allows_access(db_session: AsyncSession):
    """Direct GRANT on user_privileges gives access."""
    user = User(
        id=uuid.uuid4(),
        username="granted_user",
        password_hash=hash_password("pw"),
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()

    acl = ACLService(db_session)
    from openfmis.schemas.privilege import PrivilegeGrant

    await acl.grant_user_privilege(
        user.id,
        PrivilegeGrant(
            resource_type="fields",
            permissions={"fields.read": "GRANT", "fields.write": "DENY"},
        ),
    )

    assert await acl.check_permission(user, "fields.read", "fields") is True
    assert await acl.check_permission(user, "fields.write", "fields") is False


@pytest.mark.asyncio
async def test_user_deny_blocks_access(db_session: AsyncSession):
    """DENY on user_privileges blocks even if group grants."""
    group = Group(id=uuid.uuid4(), name="TestGroup")
    db_session.add(group)
    await db_session.flush()

    user = User(
        id=uuid.uuid4(),
        username="denied_user",
        password_hash=hash_password("pw"),
        is_active=True,
        is_superuser=False,
        group_id=group.id,
    )
    db_session.add(user)
    await db_session.flush()

    acl = ACLService(db_session)
    from openfmis.schemas.privilege import PrivilegeGrant

    # Group grants
    await acl.grant_group_privilege(
        group.id,
        PrivilegeGrant(
            resource_type="fields",
            permissions={"fields.read": "GRANT"},
        ),
    )

    # User denies
    await acl.grant_user_privilege(
        user.id,
        PrivilegeGrant(
            resource_type="fields",
            permissions={"fields.read": "DENY"},
        ),
    )

    # User-level DENY overrides group-level GRANT
    assert await acl.check_permission(user, "fields.read", "fields") is False


@pytest.mark.asyncio
async def test_group_grant_inherits(db_session: AsyncSession):
    """User inherits GRANT from their group."""
    group = Group(id=uuid.uuid4(), name="InheritGroup")
    db_session.add(group)
    await db_session.flush()

    user = User(
        id=uuid.uuid4(),
        username="inherit_user",
        password_hash=hash_password("pw"),
        is_active=True,
        is_superuser=False,
        group_id=group.id,
    )
    db_session.add(user)
    await db_session.flush()

    acl = ACLService(db_session)
    from openfmis.schemas.privilege import PrivilegeGrant

    await acl.grant_group_privilege(
        group.id,
        PrivilegeGrant(
            resource_type="fields",
            permissions={"fields.read": "GRANT"},
        ),
    )

    assert await acl.check_permission(user, "fields.read", "fields") is True


@pytest.mark.asyncio
async def test_group_hierarchy_inheritance(db_session: AsyncSession):
    """Permissions walk up: child group → parent group."""
    parent_group = Group(id=uuid.uuid4(), name="ParentOrg")
    db_session.add(parent_group)
    await db_session.flush()

    child_group = Group(id=uuid.uuid4(), name="ChildTeam", parent_id=parent_group.id)
    db_session.add(child_group)
    await db_session.flush()

    user = User(
        id=uuid.uuid4(),
        username="child_team_user",
        password_hash=hash_password("pw"),
        is_active=True,
        is_superuser=False,
        group_id=child_group.id,
    )
    db_session.add(user)
    await db_session.flush()

    acl = ACLService(db_session)
    from openfmis.schemas.privilege import PrivilegeGrant

    # Only parent group has the permission
    await acl.grant_group_privilege(
        parent_group.id,
        PrivilegeGrant(
            resource_type="fields",
            permissions={"fields.read": "GRANT"},
        ),
    )

    # Child group has ALLOW (defer to parent)
    await acl.grant_group_privilege(
        child_group.id,
        PrivilegeGrant(
            resource_type="fields",
            permissions={"fields.read": "ALLOW"},
        ),
    )

    assert await acl.check_permission(user, "fields.read", "fields") is True


@pytest.mark.asyncio
async def test_effective_permissions(db_session: AsyncSession):
    """Effective permissions merge user + group correctly."""
    group = Group(id=uuid.uuid4(), name="EffGroup")
    db_session.add(group)
    await db_session.flush()

    user = User(
        id=uuid.uuid4(),
        username="eff_user",
        password_hash=hash_password("pw"),
        is_active=True,
        is_superuser=False,
        group_id=group.id,
    )
    db_session.add(user)
    await db_session.flush()

    acl = ACLService(db_session)
    from openfmis.schemas.privilege import PrivilegeGrant

    await acl.grant_group_privilege(
        group.id,
        PrivilegeGrant(
            resource_type="fields",
            permissions={"fields.read": "GRANT", "fields.write": "GRANT", "fields.delete": "DENY"},
        ),
    )

    await acl.grant_user_privilege(
        user.id,
        PrivilegeGrant(
            resource_type="fields",
            permissions={"fields.write": "DENY"},  # User overrides group
        ),
    )

    effective = await acl.get_effective_permissions(user, "fields")
    assert effective["fields.read"] == "GRANT"  # from group
    assert effective["fields.write"] == "DENY"  # user override
    assert effective["fields.delete"] == "DENY"  # from group


# ── API endpoint tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_grant_and_check(client: AsyncClient, test_user):
    """Grant permission via API, then check it."""
    token = await _login(client)

    # Grant
    resp = await client.post(
        f"/api/v1/acl/users/{test_user.id}/privileges",
        headers=_auth(token),
        json={
            "resource_type": "fields",
            "permissions": {"fields.read": "GRANT"},
        },
    )
    assert resp.status_code == 201

    # Check
    resp = await client.get(
        "/api/v1/acl/check",
        headers=_auth(token),
        params={"permission": "fields.read", "resource_type": "fields"},
    )
    assert resp.status_code == 200
    assert resp.json()["granted"] is True


@pytest.mark.asyncio
async def test_api_check_denied(client: AsyncClient, test_user):
    """Without any grants, permission should be denied."""
    token = await _login(client)

    resp = await client.get(
        "/api/v1/acl/check",
        headers=_auth(token),
        params={"permission": "admin.system", "resource_type": "system"},
    )
    assert resp.status_code == 200
    assert resp.json()["granted"] is False


@pytest.mark.asyncio
async def test_api_list_user_privileges(client: AsyncClient, test_user):
    token = await _login(client)

    # Grant something
    await client.post(
        f"/api/v1/acl/users/{test_user.id}/privileges",
        headers=_auth(token),
        json={"resource_type": "reports", "permissions": {"reports.view": "GRANT"}},
    )

    resp = await client.get(
        f"/api/v1/acl/users/{test_user.id}/privileges",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    privs = resp.json()
    assert any(p["resource_type"] == "reports" for p in privs)


@pytest.mark.asyncio
async def test_api_revoke_user_privilege(client: AsyncClient, test_user):
    token = await _login(client)

    # Grant
    await client.post(
        f"/api/v1/acl/users/{test_user.id}/privileges",
        headers=_auth(token),
        json={"resource_type": "temp", "permissions": {"temp.do": "GRANT"}},
    )

    # Revoke
    resp = await client.delete(
        f"/api/v1/acl/users/{test_user.id}/privileges",
        headers=_auth(token),
        params={"resource_type": "temp"},
    )
    assert resp.status_code == 204

    # Verify gone
    resp = await client.get(
        f"/api/v1/acl/users/{test_user.id}/privileges",
        headers=_auth(token),
    )
    privs = resp.json()
    assert not any(p["resource_type"] == "temp" for p in privs)


@pytest.mark.asyncio
async def test_api_effective_permissions(client: AsyncClient, test_user):
    token = await _login(client)

    await client.post(
        f"/api/v1/acl/users/{test_user.id}/privileges",
        headers=_auth(token),
        json={
            "resource_type": "analysis",
            "permissions": {"analysis.run": "GRANT", "analysis.delete": "DENY"},
        },
    )

    resp = await client.get(
        "/api/v1/acl/effective",
        headers=_auth(token),
        params={"resource_type": "analysis"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["permissions"]["analysis.run"] == "GRANT"
    assert data["permissions"]["analysis.delete"] == "DENY"


@pytest.mark.asyncio
async def test_api_grant_requires_change_object_acls(client: AsyncClient, db_session):
    """User without change_object_acls cannot grant or revoke privileges."""
    no_acl_group = Group(id=uuid.uuid4(), name="NoACLAdminGroup")
    db_session.add(no_acl_group)
    await db_session.flush()

    user = User(
        id=uuid.uuid4(),
        username="no_acl_admin",
        email="noacl@test.com",
        password_hash=hash_password("pass123"),
        full_name="No ACL Admin",
        is_active=True,
        is_superuser=False,
        group_id=no_acl_group.id,
    )
    db_session.add(user)
    await db_session.flush()

    token = await _login(client, "no_acl_admin", "pass123")

    # Grant user privilege should fail
    resp = await client.post(
        f"/api/v1/acl/users/{user.id}/privileges",
        headers=_auth(token),
        json={
            "resource_type": "fields",
            "permissions": {"fields.read": "GRANT"},
        },
    )
    assert resp.status_code == 403

    # Revoke user privilege should fail
    resp = await client.delete(
        f"/api/v1/acl/users/{user.id}/privileges",
        headers=_auth(token),
        params={"resource_type": "fields"},
    )
    assert resp.status_code == 403

    # Grant group privilege should fail
    resp = await client.post(
        f"/api/v1/acl/groups/{no_acl_group.id}/privileges",
        headers=_auth(token),
        json={
            "resource_type": "fields",
            "permissions": {"fields.read": "GRANT"},
        },
    )
    assert resp.status_code == 403

    # But check/effective/list are still OK (read-only)
    resp = await client.get(
        "/api/v1/acl/check",
        headers=_auth(token),
        params={"permission": "fields.read", "resource_type": "fields"},
    )
    assert resp.status_code == 200

    resp = await client.get(
        f"/api/v1/acl/users/{user.id}/privileges",
        headers=_auth(token),
    )
    assert resp.status_code == 200


# ── Privilege ceiling tests ──────────────────────────────────


@pytest.mark.asyncio
async def test_privilege_ceiling_parent_has_grant(db_session: AsyncSession):
    """Child group can receive GRANT if parent holds it."""
    parent = Group(id=uuid.uuid4(), name="CeilingParent")
    db_session.add(parent)
    await db_session.flush()

    child = Group(id=uuid.uuid4(), name="CeilingChild", parent_id=parent.id)
    db_session.add(child)
    await db_session.flush()

    acl = ACLService(db_session)

    # Parent gets GRANT
    await acl.grant_group_privilege(
        parent.id,
        PrivilegeGrant(
            resource_type="fields",
            permissions={"fields.read": "GRANT"},
        ),
    )

    # Child should be allowed to get GRANT (parent has it)
    priv = await acl.grant_group_privilege(
        child.id,
        PrivilegeGrant(
            resource_type="fields",
            permissions={"fields.read": "GRANT"},
        ),
    )
    assert priv.permissions["fields.read"] == "GRANT"


@pytest.mark.asyncio
async def test_privilege_ceiling_parent_lacks_grant(db_session: AsyncSession):
    """Child group cannot receive GRANT if parent does not hold it."""
    parent = Group(id=uuid.uuid4(), name="CeilingParentNoGrant")
    db_session.add(parent)
    await db_session.flush()

    child = Group(id=uuid.uuid4(), name="CeilingChildBlocked", parent_id=parent.id)
    db_session.add(child)
    await db_session.flush()

    acl = ACLService(db_session)

    # Parent has NO grants for fields.write
    # Child tries to get GRANT — should fail
    with pytest.raises(ValidationError, match="privilege ceiling"):
        await acl.grant_group_privilege(
            child.id,
            PrivilegeGrant(
                resource_type="fields",
                permissions={"fields.write": "GRANT"},
            ),
        )


@pytest.mark.asyncio
async def test_privilege_ceiling_root_group_unconstrained(
    db_session: AsyncSession,
):
    """Root group (no parent) can have any privilege — no ceiling."""
    root = Group(id=uuid.uuid4(), name="CeilingRoot")
    db_session.add(root)
    await db_session.flush()

    acl = ACLService(db_session)
    priv = await acl.grant_group_privilege(
        root.id,
        PrivilegeGrant(
            resource_type="anything",
            permissions={"anything.admin": "GRANT"},
        ),
    )
    assert priv.permissions["anything.admin"] == "GRANT"
