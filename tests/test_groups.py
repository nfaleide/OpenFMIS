"""GroupService + Group API endpoint tests — including recursive CTE hierarchy."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import ValidationError
from openfmis.models.group import Group
from openfmis.models.user import User
from openfmis.security.password import hash_password
from openfmis.services.group import GroupService


async def _login(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/login",
        json={"username": "testuser", "password": "testpassword123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_group(client: AsyncClient, test_user):
    token = await _login(client)
    resp = await client.post(
        "/api/v1/groups",
        headers=_auth(token),
        json={"name": "Root Org", "description": "Top-level organization"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Root Org"
    assert data["parent_id"] is None


@pytest.mark.asyncio
async def test_create_child_group(client: AsyncClient, test_user):
    token = await _login(client)

    # Create parent
    parent_resp = await client.post(
        "/api/v1/groups",
        headers=_auth(token),
        json={"name": "Parent Group"},
    )
    parent_id = parent_resp.json()["id"]

    # Create child
    child_resp = await client.post(
        "/api/v1/groups",
        headers=_auth(token),
        json={"name": "Child Group", "parent_id": parent_id},
    )
    assert child_resp.status_code == 201
    assert child_resp.json()["parent_id"] == parent_id


@pytest.mark.asyncio
async def test_list_groups(client: AsyncClient, test_user):
    token = await _login(client)

    # Create a couple groups
    await client.post("/api/v1/groups", headers=_auth(token), json={"name": "Alpha"})
    await client.post("/api/v1/groups", headers=_auth(token), json={"name": "Beta"})

    resp = await client.get("/api/v1/groups", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_list_root_groups(client: AsyncClient, test_user):
    token = await _login(client)

    parent_resp = await client.post("/api/v1/groups", headers=_auth(token), json={"name": "RootA"})
    parent_id = parent_resp.json()["id"]
    await client.post(
        "/api/v1/groups", headers=_auth(token), json={"name": "ChildA", "parent_id": parent_id}
    )

    resp = await client.get("/api/v1/groups?root_only=true", headers=_auth(token))
    assert resp.status_code == 200
    # All items should have no parent
    for g in resp.json()["items"]:
        assert g["parent_id"] is None


@pytest.mark.asyncio
async def test_get_group(client: AsyncClient, test_user):
    token = await _login(client)
    create_resp = await client.post("/api/v1/groups", headers=_auth(token), json={"name": "GetMe"})
    group_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/groups/{group_id}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["name"] == "GetMe"


@pytest.mark.asyncio
async def test_update_group(client: AsyncClient, test_user):
    token = await _login(client)
    create_resp = await client.post(
        "/api/v1/groups", headers=_auth(token), json={"name": "Original"}
    )
    group_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/groups/{group_id}",
        headers=_auth(token),
        json={"name": "Renamed"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"


@pytest.mark.asyncio
async def test_delete_group(client: AsyncClient, test_user):
    token = await _login(client)
    create_resp = await client.post(
        "/api/v1/groups", headers=_auth(token), json={"name": "DeleteMe"}
    )
    group_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/v1/groups/{group_id}", headers=_auth(token))
    assert resp.status_code == 204

    get_resp = await client.get(f"/api/v1/groups/{group_id}", headers=_auth(token))
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_group_hierarchy_ancestors(client: AsyncClient, test_user):
    """Test 3-level hierarchy: Grandparent → Parent → Child, query ancestors of Child."""
    token = await _login(client)

    gp_resp = await client.post(
        "/api/v1/groups", headers=_auth(token), json={"name": "Grandparent"}
    )
    gp_id = gp_resp.json()["id"]

    p_resp = await client.post(
        "/api/v1/groups", headers=_auth(token), json={"name": "Parent", "parent_id": gp_id}
    )
    p_id = p_resp.json()["id"]

    c_resp = await client.post(
        "/api/v1/groups", headers=_auth(token), json={"name": "Child", "parent_id": p_id}
    )
    c_id = c_resp.json()["id"]

    resp = await client.get(f"/api/v1/groups/{c_id}/ancestors", headers=_auth(token))
    assert resp.status_code == 200
    ancestors = resp.json()["ancestors"]
    assert len(ancestors) == 2
    # Root first, then parent
    assert ancestors[0]["name"] == "Grandparent"
    assert ancestors[1]["name"] == "Parent"


@pytest.mark.asyncio
async def test_group_hierarchy_descendants(client: AsyncClient, test_user):
    """Test descendants query — Grandparent should list Parent + Child."""
    token = await _login(client)

    gp_resp = await client.post("/api/v1/groups", headers=_auth(token), json={"name": "GPDesc"})
    gp_id = gp_resp.json()["id"]

    p_resp = await client.post(
        "/api/v1/groups", headers=_auth(token), json={"name": "PDesc", "parent_id": gp_id}
    )
    p_id = p_resp.json()["id"]

    await client.post(
        "/api/v1/groups", headers=_auth(token), json={"name": "CDesc", "parent_id": p_id}
    )

    resp = await client.get(f"/api/v1/groups/{gp_id}/descendants", headers=_auth(token))
    assert resp.status_code == 200
    descendants = resp.json()
    assert len(descendants) == 2
    names = {d["name"] for d in descendants}
    assert "PDesc" in names
    assert "CDesc" in names


@pytest.mark.asyncio
async def test_group_tree(client: AsyncClient, test_user):
    """Test nested tree endpoint."""
    token = await _login(client)

    root_resp = await client.post("/api/v1/groups", headers=_auth(token), json={"name": "TreeRoot"})
    root_id = root_resp.json()["id"]
    await client.post(
        "/api/v1/groups", headers=_auth(token), json={"name": "TreeChild", "parent_id": root_id}
    )

    resp = await client.get(f"/api/v1/groups/tree?root_id={root_id}", headers=_auth(token))
    assert resp.status_code == 200
    tree = resp.json()
    assert len(tree) == 1  # One root
    assert tree[0]["name"] == "TreeRoot"
    assert len(tree[0]["children"]) == 1
    assert tree[0]["children"][0]["name"] == "TreeChild"


@pytest.mark.asyncio
async def test_prevent_self_parent(client: AsyncClient, test_user):
    token = await _login(client)
    create_resp = await client.post(
        "/api/v1/groups", headers=_auth(token), json={"name": "SelfRef"}
    )
    group_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/groups/{group_id}",
        headers=_auth(token),
        json={"parent_id": group_id},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_prevent_circular_hierarchy(client: AsyncClient, test_user):
    """A → B → C, then try to set A.parent = C — should fail."""
    token = await _login(client)

    a_resp = await client.post("/api/v1/groups", headers=_auth(token), json={"name": "A"})
    a_id = a_resp.json()["id"]

    b_resp = await client.post(
        "/api/v1/groups", headers=_auth(token), json={"name": "B", "parent_id": a_id}
    )
    b_id = b_resp.json()["id"]

    c_resp = await client.post(
        "/api/v1/groups", headers=_auth(token), json={"name": "C", "parent_id": b_id}
    )
    c_id = c_resp.json()["id"]

    # Try to make A a child of C (circular)
    resp = await client.patch(
        f"/api/v1/groups/{a_id}",
        headers=_auth(token),
        json={"parent_id": c_id},
    )
    assert resp.status_code == 422


# ── Group cascade behavior tests ─────────────────────────────────────────��───


@pytest.mark.asyncio
async def test_delete_group_with_children_blocked(db_session: AsyncSession):
    """Cannot delete a group that has active child groups."""
    svc = GroupService(db_session)
    parent = Group(id=uuid.uuid4(), name="CascadeParent")
    db_session.add(parent)
    await db_session.flush()

    child = Group(id=uuid.uuid4(), name="CascadeChild", parent_id=parent.id)
    db_session.add(child)
    await db_session.flush()

    with pytest.raises(ValidationError, match="active child groups"):
        await svc.soft_delete(parent.id)


@pytest.mark.asyncio
async def test_delete_group_with_users_blocked(db_session: AsyncSession):
    """Cannot delete a group that has active users."""
    svc = GroupService(db_session)
    group = Group(id=uuid.uuid4(), name="UserGroup")
    db_session.add(group)
    await db_session.flush()

    user = User(
        id=uuid.uuid4(),
        username="cascadeuser",
        email="cascade@test.com",
        password_hash=hash_password("pass123"),
        full_name="Cascade User",
        is_active=True,
        is_superuser=False,
        group_id=group.id,
    )
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(ValidationError, match="active users"):
        await svc.soft_delete(group.id)


@pytest.mark.asyncio
async def test_delete_group_empty_succeeds(db_session: AsyncSession):
    """Can delete a group with no children and no users."""
    svc = GroupService(db_session)
    group = Group(id=uuid.uuid4(), name="EmptyGroup")
    db_session.add(group)
    await db_session.flush()

    await svc.soft_delete(group.id)
    # Verify it's deleted
    from openfmis.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        await svc.get_by_id(group.id)


@pytest.mark.asyncio
async def test_delete_group_after_children_removed(db_session: AsyncSession):
    """Can delete a parent group after its children have been soft-deleted."""
    svc = GroupService(db_session)
    parent = Group(id=uuid.uuid4(), name="ParentAfterRemove")
    db_session.add(parent)
    await db_session.flush()

    child = Group(id=uuid.uuid4(), name="ChildToRemove", parent_id=parent.id)
    db_session.add(child)
    await db_session.flush()

    # Delete the child first
    await svc.soft_delete(child.id)
    # Now parent should be deletable
    await svc.soft_delete(parent.id)

    from openfmis.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        await svc.get_by_id(parent.id)


@pytest.mark.asyncio
async def test_api_delete_group_with_children_returns_422(client: AsyncClient, test_user):
    """API returns 422 when trying to delete a group with children."""
    token = await _login(client)
    parent_resp = await client.post(
        "/api/v1/groups", headers=_auth(token), json={"name": "APIParent"}
    )
    parent_id = parent_resp.json()["id"]

    await client.post(
        "/api/v1/groups",
        headers=_auth(token),
        json={"name": "APIChild", "parent_id": parent_id},
    )

    resp = await client.delete(f"/api/v1/groups/{parent_id}", headers=_auth(token))
    assert resp.status_code == 422


# ── Authorization guard tests ──────────────────────────────────────────────


async def _login_as(
    client: AsyncClient,
    username: str,
    password: str,
) -> str:
    resp = await client.post(
        "/api/v1/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_unprivileged_user_cannot_create_group(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """A user without change_group_settings cannot create groups."""
    # Create a group with NO group admin privileges
    bare_group = Group(id=uuid.uuid4(), name="BareGroup")
    db_session.add(bare_group)
    await db_session.flush()

    bare_user = User(
        id=uuid.uuid4(),
        username="bareuser",
        password_hash=hash_password("barepass123"),
        is_active=True,
        is_superuser=False,
        group_id=bare_group.id,
    )
    db_session.add(bare_user)
    await db_session.flush()

    token = await _login_as(client, "bareuser", "barepass123")
    resp = await client.post(
        "/api/v1/groups",
        headers=_auth(token),
        json={"name": "ShouldFail"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unprivileged_user_cannot_update_group(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """A user without change_group_settings cannot update groups."""
    bare_group = Group(id=uuid.uuid4(), name="BareGroup2")
    db_session.add(bare_group)
    await db_session.flush()

    bare_user = User(
        id=uuid.uuid4(),
        username="bareuser2",
        password_hash=hash_password("barepass123"),
        is_active=True,
        is_superuser=False,
        group_id=bare_group.id,
    )
    db_session.add(bare_user)
    await db_session.flush()

    token = await _login_as(client, "bareuser2", "barepass123")
    resp = await client.patch(
        f"/api/v1/groups/{bare_group.id}",
        headers=_auth(token),
        json={"name": "Renamed"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unprivileged_user_cannot_delete_group(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """A user without change_group_settings cannot delete groups."""
    bare_group = Group(id=uuid.uuid4(), name="BareGroup3")
    db_session.add(bare_group)
    await db_session.flush()

    bare_user = User(
        id=uuid.uuid4(),
        username="bareuser3",
        password_hash=hash_password("barepass123"),
        is_active=True,
        is_superuser=False,
        group_id=bare_group.id,
    )
    db_session.add(bare_user)
    await db_session.flush()

    token = await _login_as(client, "bareuser3", "barepass123")
    resp = await client.delete(
        f"/api/v1/groups/{bare_group.id}",
        headers=_auth(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_privileged_user_can_manage_groups(
    client: AsyncClient,
    test_user,
):
    """test_user has change_group_settings via test_group — can CRUD."""
    token = await _login(client)
    # Create
    resp = await client.post(
        "/api/v1/groups",
        headers=_auth(token),
        json={"name": "PrivTest"},
    )
    assert resp.status_code == 201
    gid = resp.json()["id"]

    # Update
    resp = await client.patch(
        f"/api/v1/groups/{gid}",
        headers=_auth(token),
        json={"name": "PrivTestRenamed"},
    )
    assert resp.status_code == 200

    # Delete
    resp = await client.delete(
        f"/api/v1/groups/{gid}",
        headers=_auth(token),
    )
    assert resp.status_code == 204
