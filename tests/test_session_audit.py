"""Session audit log tests — login/logout tracking."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.user import User
from openfmis.security.password import hash_password
from openfmis.services.session_audit import SessionAuditService


@pytest.fixture
async def audit_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        username="audituser",
        email="audit@test.com",
        password_hash=hash_password("auditpass123"),
        full_name="Audit User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


# ── Service tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_login(db_session: AsyncSession, audit_user: User):
    svc = SessionAuditService(db_session)
    entry = await svc.record(
        audit_user.id, "login", ip_address="192.168.1.1", user_agent="TestClient/1.0"
    )
    assert entry.event_type == "login"
    assert entry.ip_address == "192.168.1.1"
    assert entry.user_agent == "TestClient/1.0"


@pytest.mark.asyncio
async def test_record_logout(db_session: AsyncSession, audit_user: User):
    svc = SessionAuditService(db_session)
    entry = await svc.record(audit_user.id, "logout", jti="test-jti-abc")
    assert entry.event_type == "logout"
    assert entry.jti == "test-jti-abc"


@pytest.mark.asyncio
async def test_list_for_user(db_session: AsyncSession, audit_user: User):
    svc = SessionAuditService(db_session)
    await svc.record(audit_user.id, "login")
    await svc.record(audit_user.id, "logout")
    await svc.record(audit_user.id, "login_failed")

    entries, total = await svc.list_for_user(audit_user.id)
    assert total == 3
    assert len(entries) == 3
    event_types = {e.event_type for e in entries}
    assert event_types == {"login", "logout", "login_failed"}


@pytest.mark.asyncio
async def test_list_filtered_by_type(db_session: AsyncSession, audit_user: User):
    svc = SessionAuditService(db_session)
    await svc.record(audit_user.id, "login")
    await svc.record(audit_user.id, "logout")
    await svc.record(audit_user.id, "login")

    entries, total = await svc.list_for_user(audit_user.id, event_type="login")
    assert total == 2


# ── API tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_creates_audit_entry(client: AsyncClient, audit_user: User, db_session):
    resp = await client.post(
        "/api/v1/login",
        json={"username": "audituser", "password": "auditpass123"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    # Check audit log
    resp2 = await client.get(
        "/api/v1/auth/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["total"] >= 1
    assert any(e["event_type"] == "login" for e in data["items"])


@pytest.mark.asyncio
async def test_logout_creates_audit_entry(client: AsyncClient, audit_user: User, db_session):
    # Login first
    resp = await client.post(
        "/api/v1/login",
        json={"username": "audituser", "password": "auditpass123"},
    )
    token = resp.json()["access_token"]

    # Logout
    resp2 = await client.delete(
        "/api/v1/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    # Logout may be POST or DELETE, check which one works
    if resp2.status_code == 405:
        resp2 = await client.post(
            "/api/v1/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp2.status_code == 204

    # Login again to check audit log
    resp3 = await client.post(
        "/api/v1/login",
        json={"username": "audituser", "password": "auditpass123"},
    )
    token2 = resp3.json()["access_token"]

    resp4 = await client.get(
        "/api/v1/auth/sessions",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp4.status_code == 200
    events = [e["event_type"] for e in resp4.json()["items"]]
    assert "logout" in events


@pytest.mark.asyncio
async def test_failed_login_creates_audit_entry(client: AsyncClient, audit_user: User, db_session):
    # Try wrong password
    resp = await client.post(
        "/api/v1/login",
        json={"username": "audituser", "password": "wrongpassword"},
    )
    assert resp.status_code == 401

    # Login correctly to check
    resp2 = await client.post(
        "/api/v1/login",
        json={"username": "audituser", "password": "auditpass123"},
    )
    token = resp2.json()["access_token"]

    resp3 = await client.get(
        "/api/v1/auth/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    events = [e["event_type"] for e in resp3.json()["items"]]
    assert "login_failed" in events
