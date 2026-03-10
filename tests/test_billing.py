"""Billing service and API tests — credit accounts, ledger, price catalog."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.user import User
from openfmis.schemas.billing import CreditAdd, CreditConsume, CreditRefund, PriceSet
from openfmis.security.password import hash_password
from openfmis.services.billing import (
    CreditAccountingService,
    InsufficientCreditsError,
    PricingService,
)

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
async def regular_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        username="billuser",
        email="billuser@example.com",
        password_hash=hash_password("testpassword123"),
        full_name="Bill User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        username="billadmin",
        email="billadmin@example.com",
        password_hash=hash_password("adminpassword123"),
        full_name="Bill Admin",
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


# ── CreditAccountingService unit tests ───────────────────────────────────────


@pytest.mark.asyncio
async def test_get_or_create_account_new(db_session: AsyncSession, regular_user: User):
    svc = CreditAccountingService(db_session)
    account = await svc.get_or_create_account("user", regular_user.id)
    assert account.owner_type == "user"
    assert account.owner_id == regular_user.id
    assert account.balance == 0


@pytest.mark.asyncio
async def test_get_or_create_account_idempotent(db_session: AsyncSession, regular_user: User):
    svc = CreditAccountingService(db_session)
    a1 = await svc.get_or_create_account("user", regular_user.id)
    a2 = await svc.get_or_create_account("user", regular_user.id)
    assert a1.id == a2.id


@pytest.mark.asyncio
async def test_add_credits(db_session: AsyncSession, regular_user: User):
    svc = CreditAccountingService(db_session)
    entry = await svc.add_credits(
        "user", regular_user.id, CreditAdd(amount=100, reference="inv-001")
    )
    assert entry.entry_type == "purchase"
    assert entry.amount == 100
    assert entry.balance_after == 100

    account = await svc.get_or_create_account("user", regular_user.id)
    assert account.balance == 100


@pytest.mark.asyncio
async def test_consume_credits(db_session: AsyncSession, regular_user: User):
    svc = CreditAccountingService(db_session)
    await svc.add_credits("user", regular_user.id, CreditAdd(amount=50))
    entry = await svc.consume_credits(
        "user", regular_user.id, CreditConsume(amount=20, reference="scene:abc")
    )
    assert entry.entry_type == "consume"
    assert entry.amount == -20
    assert entry.balance_after == 30


@pytest.mark.asyncio
async def test_consume_credits_insufficient(db_session: AsyncSession, regular_user: User):
    svc = CreditAccountingService(db_session)
    await svc.add_credits("user", regular_user.id, CreditAdd(amount=10))
    with pytest.raises(InsufficientCreditsError) as exc_info:
        await svc.consume_credits("user", regular_user.id, CreditConsume(amount=50))
    assert exc_info.value.balance == 10
    assert exc_info.value.requested == 50


@pytest.mark.asyncio
async def test_consume_zero_balance_fails(db_session: AsyncSession, regular_user: User):
    svc = CreditAccountingService(db_session)
    with pytest.raises(InsufficientCreditsError):
        await svc.consume_credits("user", regular_user.id, CreditConsume(amount=1))


@pytest.mark.asyncio
async def test_refund_credits(db_session: AsyncSession, regular_user: User):
    svc = CreditAccountingService(db_session)
    await svc.add_credits("user", regular_user.id, CreditAdd(amount=50))
    await svc.consume_credits("user", regular_user.id, CreditConsume(amount=20))
    entry = await svc.refund_credits(
        "user", regular_user.id, CreditRefund(amount=10, reference="scene:abc")
    )
    assert entry.entry_type == "refund"
    assert entry.amount == 10
    assert entry.balance_after == 40


@pytest.mark.asyncio
async def test_get_ledger(db_session: AsyncSession, regular_user: User):
    svc = CreditAccountingService(db_session)
    await svc.add_credits("user", regular_user.id, CreditAdd(amount=100))
    await svc.consume_credits("user", regular_user.id, CreditConsume(amount=30))
    entries, total = await svc.get_ledger("user", regular_user.id)
    assert total == 2
    assert len(entries) == 2
    # Most recent first
    assert entries[0].entry_type == "consume"


@pytest.mark.asyncio
async def test_get_ledger_empty_account(db_session: AsyncSession, regular_user: User):
    svc = CreditAccountingService(db_session)
    entries, total = await svc.get_ledger("user", regular_user.id)
    assert total == 0
    assert entries == []


@pytest.mark.asyncio
async def test_group_account(db_session: AsyncSession):
    svc = CreditAccountingService(db_session)
    group_id = uuid.uuid4()
    account = await svc.get_or_create_account("group", group_id)
    assert account.owner_type == "group"
    entry = await svc.add_credits("group", group_id, CreditAdd(amount=200))
    assert entry.balance_after == 200


# ── PricingService unit tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_prices_active_only(db_session: AsyncSession):
    svc = PricingService(db_session)
    await svc.set_price(
        "scene_analysis", PriceSet(credit_cost=10, description="Satellite analysis")
    )
    await svc.set_price("field_export", PriceSet(credit_cost=1))
    await db_session.flush()

    prices = await svc.list_prices(active_only=True)
    ops = {p.operation for p in prices}
    assert "scene_analysis" in ops
    assert "field_export" in ops


@pytest.mark.asyncio
async def test_get_price(db_session: AsyncSession):
    svc = PricingService(db_session)
    await svc.set_price("scene_analysis", PriceSet(credit_cost=10))
    await db_session.flush()

    item = await svc.get_price("scene_analysis")
    assert item is not None
    assert item.credit_cost == 10


@pytest.mark.asyncio
async def test_get_price_not_found(db_session: AsyncSession):
    svc = PricingService(db_session)
    item = await svc.get_price("nonexistent_operation")
    assert item is None


@pytest.mark.asyncio
async def test_get_credit_cost(db_session: AsyncSession):
    svc = PricingService(db_session)
    await svc.set_price("scene_analysis", PriceSet(credit_cost=10))
    await db_session.flush()

    cost = await svc.get_credit_cost("scene_analysis")
    assert cost == 10
    cost_unknown = await svc.get_credit_cost("unknown")
    assert cost_unknown == 0


@pytest.mark.asyncio
async def test_set_price_new(db_session: AsyncSession):
    svc = PricingService(db_session)
    item = await svc.set_price("custom_op", PriceSet(credit_cost=5, description="Custom"))
    assert item.operation == "custom_op"
    assert item.credit_cost == 5
    assert item.is_active is True


@pytest.mark.asyncio
async def test_set_price_update(db_session: AsyncSession):
    svc = PricingService(db_session)
    await svc.set_price("custom_op2", PriceSet(credit_cost=5))
    updated = await svc.set_price("custom_op2", PriceSet(credit_cost=15))
    assert updated.credit_cost == 15


@pytest.mark.asyncio
async def test_deactivate_price(db_session: AsyncSession):
    svc = PricingService(db_session)
    await svc.set_price("to_deactivate", PriceSet(credit_cost=3))
    item = await svc.deactivate("to_deactivate")
    assert item.is_active is False
    cost = await svc.get_credit_cost("to_deactivate")
    assert cost == 0  # inactive => 0


# ── API endpoint tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_get_account(client: AsyncClient, regular_user: User):
    token = await _login(client, "billuser", "testpassword123")
    resp = await client.get(
        f"/api/v1/billing/accounts/user/{regular_user.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["owner_type"] == "user"
    assert data["balance"] == 0


@pytest.mark.asyncio
async def test_api_get_other_account_denied(client: AsyncClient, regular_user: User):
    token = await _login(client, "billuser", "testpassword123")
    other_id = uuid.uuid4()
    resp = await client.get(
        f"/api/v1/billing/accounts/user/{other_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_api_add_credits_superuser(client: AsyncClient, admin_user: User, regular_user: User):
    token = await _login(client, "billadmin", "adminpassword123")
    resp = await client.post(
        f"/api/v1/billing/accounts/user/{regular_user.id}/credits",
        json={"amount": 100, "reference": "test-purchase"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["amount"] == 100
    assert data["balance_after"] == 100
    assert data["entry_type"] == "purchase"


@pytest.mark.asyncio
async def test_api_add_credits_requires_superuser(client: AsyncClient, regular_user: User):
    token = await _login(client, "billuser", "testpassword123")
    resp = await client.post(
        f"/api/v1/billing/accounts/user/{regular_user.id}/credits",
        json={"amount": 100},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_api_consume_credits(
    client: AsyncClient, admin_user: User, regular_user: User, db_session: AsyncSession
):
    # Pre-load credits
    svc = CreditAccountingService(db_session)
    await svc.add_credits("user", regular_user.id, CreditAdd(amount=50))
    await db_session.flush()

    token = await _login(client, "billuser", "testpassword123")
    resp = await client.post(
        f"/api/v1/billing/accounts/user/{regular_user.id}/consume",
        json={"amount": 20, "note": "scene analysis"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["balance_after"] == 30


@pytest.mark.asyncio
async def test_api_consume_insufficient_credits(client: AsyncClient, regular_user: User):
    token = await _login(client, "billuser", "testpassword123")
    resp = await client.post(
        f"/api/v1/billing/accounts/user/{regular_user.id}/consume",
        json={"amount": 999},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 402


@pytest.mark.asyncio
async def test_api_refund_credits(
    client: AsyncClient, admin_user: User, regular_user: User, db_session: AsyncSession
):
    svc = CreditAccountingService(db_session)
    await svc.add_credits("user", regular_user.id, CreditAdd(amount=50))
    await svc.consume_credits("user", regular_user.id, CreditConsume(amount=20))
    await db_session.flush()

    token = await _login(client, "billadmin", "adminpassword123")
    resp = await client.post(
        f"/api/v1/billing/accounts/user/{regular_user.id}/refund",
        json={"amount": 10, "reference": "refund-001"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["entry_type"] == "refund"
    assert resp.json()["balance_after"] == 40


@pytest.mark.asyncio
async def test_api_get_ledger(client: AsyncClient, regular_user: User, db_session: AsyncSession):
    svc = CreditAccountingService(db_session)
    await svc.add_credits("user", regular_user.id, CreditAdd(amount=100))
    await db_session.flush()

    token = await _login(client, "billuser", "testpassword123")
    resp = await client.get(
        f"/api/v1/billing/accounts/user/{regular_user.id}/ledger",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1


@pytest.mark.asyncio
async def test_api_list_prices(client: AsyncClient, regular_user: User, db_session: AsyncSession):
    svc = PricingService(db_session)
    await svc.set_price("scene_analysis", PriceSet(credit_cost=10))
    await db_session.flush()

    token = await _login(client, "billuser", "testpassword123")
    resp = await client.get(
        "/api/v1/billing/prices",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    ops = [p["operation"] for p in resp.json()]
    assert "scene_analysis" in ops


@pytest.mark.asyncio
async def test_api_get_price(client: AsyncClient, regular_user: User, db_session: AsyncSession):
    svc = PricingService(db_session)
    await svc.set_price("scene_analysis", PriceSet(credit_cost=10))
    await db_session.flush()

    token = await _login(client, "billuser", "testpassword123")
    resp = await client.get(
        "/api/v1/billing/prices/scene_analysis",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["credit_cost"] == 10


@pytest.mark.asyncio
async def test_api_get_price_not_found(client: AsyncClient, regular_user: User):
    token = await _login(client, "billuser", "testpassword123")
    resp = await client.get(
        "/api/v1/billing/prices/ghost_operation",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_set_price(client: AsyncClient, admin_user: User):
    token = await _login(client, "billadmin", "adminpassword123")
    resp = await client.put(
        "/api/v1/billing/prices/new_operation",
        json={"credit_cost": 7, "description": "New op"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["credit_cost"] == 7


@pytest.mark.asyncio
async def test_api_set_price_requires_superuser(client: AsyncClient, regular_user: User):
    token = await _login(client, "billuser", "testpassword123")
    resp = await client.put(
        "/api/v1/billing/prices/hack_op",
        json={"credit_cost": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_api_deactivate_price(
    client: AsyncClient, admin_user: User, db_session: AsyncSession
):
    svc = PricingService(db_session)
    await svc.set_price("temp_op", PriceSet(credit_cost=5))
    await db_session.flush()

    token = await _login(client, "billadmin", "adminpassword123")
    resp = await client.delete(
        "/api/v1/billing/prices/temp_op",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_api_requires_auth(client: AsyncClient, regular_user: User):
    resp = await client.get(f"/api/v1/billing/accounts/user/{regular_user.id}")
    assert resp.status_code == 401
