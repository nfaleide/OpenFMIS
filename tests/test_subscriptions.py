"""Subscription lifecycle tests — start, renew, cancel, expire."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.services.subscription import (
    SubscriptionNotFoundError,
    SubscriptionService,
)

# ── Service-level tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_subscription(db_session: AsyncSession, test_user):
    svc = SubscriptionService(db_session)
    sub = await svc.start(
        owner_type="user",
        owner_id=test_user.id,
        plugin_id="satshot",
        subscription_type="auto_analysis",
    )
    assert sub.status == "active"
    assert sub.plugin_id == "satshot"
    assert sub.subscription_type == "auto_analysis"
    assert sub.owner_id == test_user.id


@pytest.mark.asyncio
async def test_renew_subscription(db_session: AsyncSession, test_user):
    svc = SubscriptionService(db_session)
    sub = await svc.start(
        owner_type="user",
        owner_id=test_user.id,
        plugin_id="satshot",
        subscription_type="auto_analysis",
    )
    new_exp = datetime.now(UTC) + timedelta(days=365)
    renewed = await svc.renew(sub.id, new_expires_at=new_exp)
    assert renewed.status == "active"
    assert renewed.renewed_at is not None
    assert renewed.expires_at is not None


@pytest.mark.asyncio
async def test_cancel_subscription(db_session: AsyncSession, test_user):
    svc = SubscriptionService(db_session)
    sub = await svc.start(
        owner_type="user",
        owner_id=test_user.id,
        plugin_id="satshot",
        subscription_type="auto_analysis",
    )
    cancelled = await svc.cancel(sub.id, reason="No longer needed")
    assert cancelled.status == "cancelled"
    assert cancelled.cancelled_at is not None
    assert cancelled.cancel_reason == "No longer needed"


@pytest.mark.asyncio
async def test_expire_due(db_session: AsyncSession, test_user):
    svc = SubscriptionService(db_session)
    # Create an already-expired subscription
    sub = await svc.start(
        owner_type="user",
        owner_id=test_user.id,
        plugin_id="satshot",
        subscription_type="auto_analysis",
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    assert sub.status == "active"

    count = await svc.expire_due()
    assert count == 1

    refreshed = await svc.get(sub.id)
    assert refreshed.status == "expired"


@pytest.mark.asyncio
async def test_expire_due_skips_future(db_session: AsyncSession, test_user):
    svc = SubscriptionService(db_session)
    await svc.start(
        owner_type="user",
        owner_id=test_user.id,
        plugin_id="satshot",
        subscription_type="auto_analysis",
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    count = await svc.expire_due()
    assert count == 0


@pytest.mark.asyncio
async def test_list_for_owner(db_session: AsyncSession, test_user):
    svc = SubscriptionService(db_session)
    await svc.start(
        owner_type="user",
        owner_id=test_user.id,
        plugin_id="satshot",
        subscription_type="auto_analysis",
    )
    await svc.start(
        owner_type="user",
        owner_id=test_user.id,
        plugin_id="farmstack",
        subscription_type="data_fork",
    )
    items, total = await svc.list_for_owner("user", test_user.id)
    assert total == 2
    assert len(items) == 2


@pytest.mark.asyncio
async def test_list_for_owner_filter_plugin(
    db_session: AsyncSession,
    test_user,
):
    svc = SubscriptionService(db_session)
    await svc.start(
        owner_type="user",
        owner_id=test_user.id,
        plugin_id="satshot",
        subscription_type="auto_analysis",
    )
    await svc.start(
        owner_type="user",
        owner_id=test_user.id,
        plugin_id="farmstack",
        subscription_type="data_fork",
    )
    items, total = await svc.list_for_owner(
        "user",
        test_user.id,
        plugin_id="satshot",
    )
    assert total == 1
    assert items[0].plugin_id == "satshot"


@pytest.mark.asyncio
async def test_get_not_found(db_session: AsyncSession):
    svc = SubscriptionService(db_session)
    with pytest.raises(SubscriptionNotFoundError):
        await svc.get(uuid.uuid4())


# ── API-level tests ─────────────────────────────────────────────────────────


async def _login(
    client: AsyncClient,
    username: str = "testuser",
    password: str = "testpassword123",
) -> str:
    resp = await client.post(
        "/api/v1/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_api_start_subscription(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user,
):
    token = await _login(client)
    resp = await client.post(
        "/api/v1/subscriptions",
        headers=_auth(token),
        json={
            "owner_type": "user",
            "owner_id": str(test_user.id),
            "plugin_id": "satshot",
            "subscription_type": "auto_analysis",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "active"
    assert data["plugin_id"] == "satshot"


@pytest.mark.asyncio
async def test_api_cancel_subscription(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user,
):
    token = await _login(client)
    # Create
    resp = await client.post(
        "/api/v1/subscriptions",
        headers=_auth(token),
        json={
            "owner_type": "user",
            "owner_id": str(test_user.id),
            "plugin_id": "satshot",
            "subscription_type": "auto_analysis",
        },
    )
    sub_id = resp.json()["id"]

    # Cancel
    resp = await client.post(
        f"/api/v1/subscriptions/{sub_id}/cancel",
        headers=_auth(token),
        json={"reason": "testing"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_api_list_subscriptions(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user,
):
    token = await _login(client)
    # Create two
    for st in ("auto_analysis", "data_fork"):
        await client.post(
            "/api/v1/subscriptions",
            headers=_auth(token),
            json={
                "owner_type": "user",
                "owner_id": str(test_user.id),
                "plugin_id": "satshot",
                "subscription_type": st,
            },
        )
    resp = await client.get(
        "/api/v1/subscriptions",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_api_expire_requires_superuser(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user,
):
    token = await _login(client)
    resp = await client.post(
        "/api/v1/subscriptions/expire-due",
        headers=_auth(token),
    )
    assert resp.status_code in (401, 403)
