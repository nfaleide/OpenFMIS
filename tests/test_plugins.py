"""Plugin registry service and API tests."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.user import User
from openfmis.schemas.plugin import PluginRegister, PluginUpdate
from openfmis.security.password import hash_password
from openfmis.services.plugin import PluginAlreadyExistsError, PluginNotFoundError, PluginService

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
async def regular_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        username="pluginuser",
        email="pluginuser@example.com",
        password_hash=hash_password("testpassword123"),
        full_name="Plugin User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def super_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        username="pluginadmin",
        email="pluginadmin@example.com",
        password_hash=hash_password("adminpassword123"),
        full_name="Plugin Admin",
        is_active=True,
        is_superuser=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _login(client: AsyncClient, username: str, password: str) -> str:
    resp = await client.post("/api/v1/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


_REGISTER = PluginRegister(
    slug="test-plugin",
    name="Test Plugin",
    version="1.0.0",
    description="A test plugin",
    manifest={"capabilities": ["read"]},
)


# ── PluginService unit tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_plugin(db_session: AsyncSession):
    svc = PluginService(db_session)
    plugin = await svc.register(_REGISTER)
    assert plugin.id is not None
    assert plugin.slug == "test-plugin"
    assert plugin.version == "1.0.0"
    assert plugin.is_active is True
    assert plugin.manifest == {"capabilities": ["read"]}


@pytest.mark.asyncio
async def test_register_duplicate_raises(db_session: AsyncSession):
    svc = PluginService(db_session)
    await svc.register(_REGISTER)
    with pytest.raises(PluginAlreadyExistsError):
        await svc.register(_REGISTER)


@pytest.mark.asyncio
async def test_list_plugins(db_session: AsyncSession):
    svc = PluginService(db_session)
    await svc.register(_REGISTER)
    plugins = await svc.list_plugins()
    assert any(p.slug == "test-plugin" for p in plugins)


@pytest.mark.asyncio
async def test_list_plugins_active_only(db_session: AsyncSession):
    svc = PluginService(db_session)
    plugin = await svc.register(_REGISTER)
    # Deactivate it
    plugin.is_active = False
    await db_session.flush()

    active = await svc.list_plugins(active_only=True)
    assert not any(p.slug == "test-plugin" for p in active)

    all_plugins = await svc.list_plugins(active_only=False)
    assert any(p.slug == "test-plugin" for p in all_plugins)


@pytest.mark.asyncio
async def test_get_plugin(db_session: AsyncSession):
    svc = PluginService(db_session)
    await svc.register(_REGISTER)
    plugin = await svc.get_plugin("test-plugin")
    assert plugin is not None
    assert plugin.name == "Test Plugin"


@pytest.mark.asyncio
async def test_get_plugin_not_found(db_session: AsyncSession):
    svc = PluginService(db_session)
    result = await svc.get_plugin("nonexistent-plugin")
    assert result is None


@pytest.mark.asyncio
async def test_update_plugin(db_session: AsyncSession):
    svc = PluginService(db_session)
    await svc.register(_REGISTER)
    updated = await svc.update("test-plugin", PluginUpdate(version="2.0.0", description="Updated"))
    assert updated.version == "2.0.0"
    assert updated.description == "Updated"
    assert updated.name == "Test Plugin"  # unchanged


@pytest.mark.asyncio
async def test_update_plugin_not_found(db_session: AsyncSession):
    svc = PluginService(db_session)
    with pytest.raises(PluginNotFoundError):
        await svc.update("ghost-plugin", PluginUpdate(version="1.0.0"))


@pytest.mark.asyncio
async def test_set_active_deactivate(db_session: AsyncSession):
    svc = PluginService(db_session)
    await svc.register(_REGISTER)
    plugin = await svc.set_active("test-plugin", False)
    assert plugin.is_active is False


@pytest.mark.asyncio
async def test_set_active_activate(db_session: AsyncSession):
    svc = PluginService(db_session)
    p = await svc.register(_REGISTER)
    p.is_active = False
    await db_session.flush()
    plugin = await svc.set_active("test-plugin", True)
    assert plugin.is_active is True


@pytest.mark.asyncio
async def test_set_active_not_found(db_session: AsyncSession):
    svc = PluginService(db_session)
    with pytest.raises(PluginNotFoundError):
        await svc.set_active("ghost", True)


@pytest.mark.asyncio
async def test_unregister_plugin(db_session: AsyncSession):
    svc = PluginService(db_session)
    await svc.register(_REGISTER)
    await svc.unregister("test-plugin")
    assert await svc.get_plugin("test-plugin") is None


@pytest.mark.asyncio
async def test_unregister_not_found(db_session: AsyncSession):
    svc = PluginService(db_session)
    with pytest.raises(PluginNotFoundError):
        await svc.unregister("ghost-plugin")


# ── EventBus tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_event_bus_emit():
    from openfmis.core.events import EventBus

    bus = EventBus()
    received = []

    @bus.on("test.event")
    async def handler(payload: dict) -> None:
        received.append(payload)

    await bus.emit("test.event", {"key": "value"})
    assert received == [{"key": "value"}]


@pytest.mark.asyncio
async def test_event_bus_no_handlers():
    from openfmis.core.events import EventBus

    bus = EventBus()
    # Should not raise
    await bus.emit("empty.event", {})


@pytest.mark.asyncio
async def test_event_bus_handler_exception_does_not_propagate():
    from openfmis.core.events import EventBus

    bus = EventBus()

    @bus.on("bad.event")
    async def bad_handler(payload: dict) -> None:
        raise RuntimeError("boom")

    # Should not raise — exceptions are logged, not propagated
    await bus.emit("bad.event", {})


@pytest.mark.asyncio
async def test_event_bus_multiple_handlers():
    from openfmis.core.events import EventBus

    bus = EventBus()
    calls = []

    @bus.on("multi.event")
    async def h1(payload: dict) -> None:
        calls.append("h1")

    @bus.on("multi.event")
    async def h2(payload: dict) -> None:
        calls.append("h2")

    await bus.emit("multi.event", {})
    assert set(calls) == {"h1", "h2"}


# ── API endpoint tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_register_plugin(client: AsyncClient, super_user: User):
    token = await _login(client, "pluginadmin", "adminpassword123")
    resp = await client.post(
        "/api/v1/plugins",
        json={"slug": "api-plugin", "name": "API Plugin", "version": "0.1.0"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["slug"] == "api-plugin"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_api_register_duplicate(client: AsyncClient, super_user: User):
    token = await _login(client, "pluginadmin", "adminpassword123")
    payload = {"slug": "dup-plugin", "name": "Dup", "version": "1.0.0"}
    await client.post("/api/v1/plugins", json=payload, headers={"Authorization": f"Bearer {token}"})
    resp = await client.post(
        "/api/v1/plugins", json=payload, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_api_register_requires_superuser(client: AsyncClient, regular_user: User):
    token = await _login(client, "pluginuser", "testpassword123")
    resp = await client.post(
        "/api/v1/plugins",
        json={"slug": "forbidden", "name": "Forbidden", "version": "1.0.0"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_api_list_plugins(client: AsyncClient, super_user: User, db_session: AsyncSession):
    # Pre-create a plugin in the DB
    svc = PluginService(db_session)
    await svc.register(PluginRegister(slug="listed-plugin", name="Listed", version="1.0.0"))
    await db_session.flush()

    token = await _login(client, "pluginadmin", "adminpassword123")
    resp = await client.get("/api/v1/plugins", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    slugs = [p["slug"] for p in resp.json()]
    assert "listed-plugin" in slugs


@pytest.mark.asyncio
async def test_api_list_plugins_regular_user_active_only(
    client: AsyncClient, regular_user: User, super_user: User, db_session: AsyncSession
):
    svc = PluginService(db_session)
    p = await svc.register(PluginRegister(slug="inactive-plugin", name="Inactive", version="1.0.0"))
    p.is_active = False
    await db_session.flush()

    token = await _login(client, "pluginuser", "testpassword123")
    resp = await client.get("/api/v1/plugins", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    slugs = [p["slug"] for p in resp.json()]
    assert "inactive-plugin" not in slugs


@pytest.mark.asyncio
async def test_api_get_plugin(client: AsyncClient, super_user: User, db_session: AsyncSession):
    svc = PluginService(db_session)
    await svc.register(PluginRegister(slug="single-plugin", name="Single", version="1.0.0"))
    await db_session.flush()

    token = await _login(client, "pluginadmin", "adminpassword123")
    resp = await client.get(
        "/api/v1/plugins/single-plugin", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Single"


@pytest.mark.asyncio
async def test_api_get_plugin_not_found(client: AsyncClient, super_user: User):
    token = await _login(client, "pluginadmin", "adminpassword123")
    resp = await client.get(
        "/api/v1/plugins/ghost-xyz", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_update_plugin(client: AsyncClient, super_user: User, db_session: AsyncSession):
    svc = PluginService(db_session)
    await svc.register(PluginRegister(slug="update-me", name="Old Name", version="1.0.0"))
    await db_session.flush()

    token = await _login(client, "pluginadmin", "adminpassword123")
    resp = await client.patch(
        "/api/v1/plugins/update-me",
        json={"name": "New Name", "version": "2.0.0"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"
    assert resp.json()["version"] == "2.0.0"


@pytest.mark.asyncio
async def test_api_activate_deactivate(
    client: AsyncClient, super_user: User, db_session: AsyncSession
):
    svc = PluginService(db_session)
    await svc.register(PluginRegister(slug="toggle-me", name="Toggle", version="1.0.0"))
    await db_session.flush()

    token = await _login(client, "pluginadmin", "adminpassword123")

    resp = await client.post(
        "/api/v1/plugins/toggle-me/deactivate", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    resp = await client.post(
        "/api/v1/plugins/toggle-me/activate", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True


@pytest.mark.asyncio
async def test_api_delete_plugin(client: AsyncClient, super_user: User, db_session: AsyncSession):
    svc = PluginService(db_session)
    await svc.register(PluginRegister(slug="delete-me", name="Delete", version="1.0.0"))
    await db_session.flush()

    token = await _login(client, "pluginadmin", "adminpassword123")
    resp = await client.delete(
        "/api/v1/plugins/delete-me", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 204

    resp = await client.get(
        "/api/v1/plugins/delete-me", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/plugins")
    assert resp.status_code == 401
