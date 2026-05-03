"""Billing service and API tests — credit accounts, ledger, price catalog, ACL."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.group import Group
from openfmis.models.privilege import GroupPrivilege, PermissionState
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
async def billing_group(db_session: AsyncSession) -> Group:
    group = Group(id=uuid.uuid4(), name="BillingCo")
    db_session.add(group)
    await db_session.flush()
    priv = GroupPrivilege(
        id=uuid.uuid4(),
        group_id=group.id,
        resource_type="billing",
        resource_id=None,
        permissions={
            "view_financials": "GRANT",
            "make_payments": "GRANT",
        },
    )
    db_session.add(priv)
    await db_session.flush()
    return group


@pytest.fixture
async def regular_user(db_session: AsyncSession, billing_group: Group) -> User:
    user = User(
        id=uuid.uuid4(),
        username="billuser",
        email="billuser@example.com",
        password_hash=hash_password("testpassword123"),
        full_name="Bill User",
        is_active=True,
        is_superuser=False,
        group_id=billing_group.id,
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
        "user",
        regular_user.id,
        CreditConsume(amount=20, reference="scene:abc"),
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
        "user",
        regular_user.id,
        CreditRefund(amount=10, reference="scene:abc"),
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
        "scene_analysis",
        PriceSet(credit_cost=10, description="Satellite analysis"),
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
    client: AsyncClient,
    admin_user: User,
    regular_user: User,
    db_session: AsyncSession,
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
    client: AsyncClient,
    admin_user: User,
    regular_user: User,
    db_session: AsyncSession,
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


# ── ACL enforcement tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_acl_no_priv_cannot_view(client: AsyncClient, db_session):
    """User with no billing permissions cannot view account or prices."""
    no_priv_group = Group(id=uuid.uuid4(), name="NoBillingPermsGroup")
    db_session.add(no_priv_group)
    await db_session.flush()

    user = User(
        id=uuid.uuid4(),
        username="no_billing_user",
        email="nobilling@test.com",
        password_hash=hash_password("pass123"),
        full_name="No Billing",
        is_active=True,
        is_superuser=False,
        group_id=no_priv_group.id,
    )
    db_session.add(user)
    await db_session.flush()

    token = await _login(client, "no_billing_user", "pass123")

    # Cannot view own account
    resp = await client.get(
        f"/api/v1/billing/accounts/user/{user.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403

    # Cannot view prices
    resp = await client.get(
        "/api/v1/billing/prices",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_acl_view_only_cannot_consume(client: AsyncClient, db_session):
    """User with view_financials but not make_payments cannot consume credits."""
    view_group = Group(id=uuid.uuid4(), name="ViewOnlyBillingGroup")
    db_session.add(view_group)
    await db_session.flush()

    priv = GroupPrivilege(
        id=uuid.uuid4(),
        group_id=view_group.id,
        resource_type="billing",
        resource_id=None,
        permissions={
            "view_financials": PermissionState.GRANT,
            "make_payments": PermissionState.DENY,
        },
    )
    db_session.add(priv)

    user = User(
        id=uuid.uuid4(),
        username="view_billing_user",
        email="viewbilling@test.com",
        password_hash=hash_password("pass123"),
        full_name="View Billing",
        is_active=True,
        is_superuser=False,
        group_id=view_group.id,
    )
    db_session.add(user)
    await db_session.flush()

    # Pre-load credits via service
    svc = CreditAccountingService(db_session)
    await svc.add_credits("user", user.id, CreditAdd(amount=100))
    await db_session.flush()

    token = await _login(client, "view_billing_user", "pass123")

    # Can view account
    resp = await client.get(
        f"/api/v1/billing/accounts/user/{user.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    # Cannot consume
    resp = await client.post(
        f"/api/v1/billing/accounts/user/{user.id}/consume",
        json={"amount": 10},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_acl_regular_user_cannot_set_price(client: AsyncClient, regular_user: User):
    """Even with billing permissions, regular users cannot set prices (superuser only)."""
    token = await _login(client, "billuser", "testpassword123")
    resp = await client.put(
        "/api/v1/billing/prices/attempt_op",
        json={"credit_cost": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── Reconciliation tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reconcile_consistent(db_session: AsyncSession):
    """When balance matches ledger SUM, reconciliation reports consistent."""
    svc = CreditAccountingService(db_session)
    uid = uuid.uuid4()
    await svc.add_credits("user", uid, CreditAdd(amount=100))
    await svc.consume_credits("user", uid, CreditConsume(amount=30))

    cached, derived, consistent = await svc.reconcile("user", uid)
    assert consistent is True
    assert cached == 70
    assert derived == 70


@pytest.mark.asyncio
async def test_reconcile_no_account(db_session: AsyncSession):
    """Reconciling a nonexistent account returns zeros and consistent."""
    svc = CreditAccountingService(db_session)
    cached, derived, consistent = await svc.reconcile("user", uuid.uuid4())
    assert consistent is True
    assert cached == 0
    assert derived == 0


@pytest.mark.asyncio
async def test_reconcile_corrects_drift(db_session: AsyncSession):
    """If balance drifts from ledger, reconciliation corrects it."""
    from sqlalchemy import update

    from openfmis.models.billing import CreditAccount

    svc = CreditAccountingService(db_session)
    uid = uuid.uuid4()
    await svc.add_credits("user", uid, CreditAdd(amount=100))

    # Artificially drift the balance
    account = await svc.get_account("user", uid)
    await db_session.execute(
        update(CreditAccount).where(CreditAccount.id == account.id).values(balance=999)
    )
    await db_session.flush()

    cached, derived, consistent = await svc.reconcile("user", uid)
    assert consistent is False
    assert cached == 999
    assert derived == 100

    # After reconciliation, balance should be corrected
    account_after = await svc.get_account("user", uid)
    await db_session.refresh(account_after)
    assert account_after.balance == 100


@pytest.mark.asyncio
async def test_api_reconcile_superuser(
    client: AsyncClient, admin_user: User, db_session: AsyncSession
):
    """Superuser can reconcile an account via the API."""
    svc = CreditAccountingService(db_session)
    await svc.add_credits("user", admin_user.id, CreditAdd(amount=50))
    await db_session.flush()

    token = await _login(client, "billadmin", "adminpassword123")
    resp = await client.post(
        f"/api/v1/billing/accounts/user/{admin_user.id}/reconcile",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["consistent"] is True
    assert data["corrected"] is False


@pytest.mark.asyncio
async def test_api_reconcile_requires_superuser(client: AsyncClient, regular_user: User):
    """Regular users cannot trigger reconciliation."""
    token = await _login(client, "billuser", "testpassword123")
    resp = await client.post(
        f"/api/v1/billing/accounts/user/{regular_user.id}/reconcile",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── Ledger filter tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_ledger_filter_by_type(db_session: AsyncSession, regular_user: User):
    """Ledger can be filtered by entry_type."""
    svc = CreditAccountingService(db_session)
    await svc.add_credits("user", regular_user.id, CreditAdd(amount=100))
    await svc.consume_credits("user", regular_user.id, CreditConsume(amount=30))

    entries, total = await svc.get_ledger("user", regular_user.id, entry_type="purchase")
    assert total == 1
    assert entries[0].entry_type == "purchase"


@pytest.mark.asyncio
async def test_get_ledger_filter_by_reference(db_session: AsyncSession, regular_user: User):
    """Ledger can be searched by reference substring."""
    svc = CreditAccountingService(db_session)
    await svc.add_credits("user", regular_user.id, CreditAdd(amount=100, reference="inv-2026-001"))
    await svc.add_credits("user", regular_user.id, CreditAdd(amount=50, reference="manual-topup"))

    entries, total = await svc.get_ledger("user", regular_user.id, reference_contains="inv-2026")
    assert total == 1
    assert "inv-2026" in entries[0].reference


@pytest.mark.asyncio
async def test_api_ledger_with_filters(
    client: AsyncClient, regular_user: User, admin_user: User, db_session: AsyncSession
):
    """API ledger endpoint accepts filter parameters."""
    svc = CreditAccountingService(db_session)
    await svc.add_credits("user", regular_user.id, CreditAdd(amount=100, reference="inv-filter"))
    await svc.consume_credits(
        "user", regular_user.id, CreditConsume(amount=20, reference="scene:xyz")
    )
    await db_session.flush()

    token = await _login(client, "billuser", "testpassword123")
    resp = await client.get(
        f"/api/v1/billing/accounts/user/{regular_user.id}/ledger",
        params={"entry_type": "consume"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["entry_type"] == "consume"


# ── Batch balances tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_balances_batch(db_session: AsyncSession):
    """Service returns balances for multiple owners."""
    svc = CreditAccountingService(db_session)
    uid1 = uuid.uuid4()
    uid2 = uuid.uuid4()
    uid3 = uuid.uuid4()  # no account
    await svc.add_credits("user", uid1, CreditAdd(amount=100))
    await svc.add_credits("user", uid2, CreditAdd(amount=200))

    results = await svc.get_balances_batch("user", [uid1, uid2, uid3])
    assert len(results) == 3
    balances = {r["owner_id"]: r["balance"] for r in results}
    assert balances[uid1] == 100
    assert balances[uid2] == 200
    assert balances[uid3] == 0  # no account = 0


@pytest.mark.asyncio
async def test_api_balances_batch(client: AsyncClient, admin_user: User, db_session: AsyncSession):
    """Superuser can query batch balances."""
    svc = CreditAccountingService(db_session)
    uid1 = uuid.uuid4()
    uid2 = uuid.uuid4()
    await svc.add_credits("user", uid1, CreditAdd(amount=50))
    await svc.add_credits("user", uid2, CreditAdd(amount=75))
    await db_session.flush()

    token = await _login(client, "billadmin", "adminpassword123")
    resp = await client.post(
        "/api/v1/billing/balances",
        json={"owner_type": "user", "owner_ids": [str(uid1), str(uid2)]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    balances = {item["owner_id"]: item["balance"] for item in data}
    assert balances[str(uid1)] == 50
    assert balances[str(uid2)] == 75


@pytest.mark.asyncio
async def test_api_balances_batch_requires_superuser(client: AsyncClient, regular_user: User):
    """Regular users cannot query batch balances."""
    token = await _login(client, "billuser", "testpassword123")
    resp = await client.post(
        "/api/v1/billing/balances",
        json={"owner_type": "user", "owner_ids": [str(regular_user.id)]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── Charge type registry tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_charge_types_creates_price_entries(db_session: AsyncSession):
    """sync_charge_types upserts manifest charge types into price_catalog."""
    from openfmis.plugin_sdk.manifest import ChargeType, PluginManifest

    manifest = PluginManifest(
        slug="billing-test-plugin",
        name="Billing Test",
        version="1.0.0",
        charge_types=[
            ChargeType(operation="test.analyze", description="Per-scene analysis"),
            ChargeType(operation="test.export", description="Imagery export"),
        ],
    )
    svc = PricingService(db_session)
    created = await svc.sync_charge_types(manifest)
    assert created == 2

    # Verify entries exist with module_id
    item = await svc.get_price("test.analyze")
    assert item is not None
    assert item.module_id == "billing-test-plugin"
    assert item.description == "Per-scene analysis"
    assert item.credit_cost == 0  # default, admin sets later

    item2 = await svc.get_price("test.export")
    assert item2 is not None
    assert item2.module_id == "billing-test-plugin"


@pytest.mark.asyncio
async def test_sync_charge_types_idempotent(db_session: AsyncSession):
    """Calling sync_charge_types again updates but doesn't duplicate."""
    from openfmis.plugin_sdk.manifest import ChargeType, PluginManifest

    manifest = PluginManifest(
        slug="idem-plugin",
        name="Idempotent",
        version="1.0.0",
        charge_types=[
            ChargeType(operation="idem.op", description="v1 description"),
        ],
    )
    svc = PricingService(db_session)

    # First sync
    created1 = await svc.sync_charge_types(manifest)
    assert created1 == 1

    # Set a price (admin action)
    await svc.set_price("idem.op", PriceSet(credit_cost=50))

    # Second sync with updated description
    manifest2 = PluginManifest(
        slug="idem-plugin",
        name="Idempotent",
        version="1.1.0",
        charge_types=[
            ChargeType(operation="idem.op", description="v2 description"),
        ],
    )
    created2 = await svc.sync_charge_types(manifest2)
    assert created2 == 0  # No new entries

    # Price should be preserved, description updated
    item = await svc.get_price("idem.op")
    assert item.credit_cost == 50
    assert item.description == "v2 description"
    assert item.module_id == "idem-plugin"


@pytest.mark.asyncio
async def test_list_by_module(db_session: AsyncSession):
    """list_by_module returns only prices for a specific plugin."""
    from openfmis.plugin_sdk.manifest import ChargeType, PluginManifest

    m1 = PluginManifest(
        slug="mod-a",
        name="Module A",
        version="1.0.0",
        charge_types=[ChargeType(operation="mod_a.op1", description="A op")],
    )
    m2 = PluginManifest(
        slug="mod-b",
        name="Module B",
        version="1.0.0",
        charge_types=[ChargeType(operation="mod_b.op1", description="B op")],
    )
    svc = PricingService(db_session)
    await svc.sync_charge_types(m1)
    await svc.sync_charge_types(m2)

    a_items = await svc.list_by_module("mod-a")
    assert len(a_items) == 1
    assert a_items[0].operation == "mod_a.op1"

    b_items = await svc.list_by_module("mod-b")
    assert len(b_items) == 1
    assert b_items[0].operation == "mod_b.op1"


@pytest.mark.asyncio
async def test_charge_type_in_memory_registry():
    """register_plugin populates the in-memory charge type registry."""
    from openfmis.plugin_sdk.hooks import (
        _clear_all_registries,
        list_charge_types,
        register_plugin,
    )
    from openfmis.plugin_sdk.manifest import ChargeType, PluginManifest

    _clear_all_registries()

    manifest = PluginManifest(
        slug="reg-test",
        name="Registry Test",
        version="1.0.0",
        charge_types=[
            ChargeType(operation="reg.op1", description="Op 1"),
            ChargeType(operation="reg.op2", description="Op 2"),
        ],
    )
    register_plugin(manifest)

    types = list_charge_types()
    ops = {ct.operation for ct in types}
    assert "reg.op1" in ops
    assert "reg.op2" in ops

    # Verify plugin_slug is set
    for ct in types:
        if ct.operation in ("reg.op1", "reg.op2"):
            assert ct.plugin_slug == "reg-test"

    _clear_all_registries()


@pytest.mark.asyncio
async def test_api_charge_types_endpoint(client: AsyncClient, admin_user: User):
    """GET /billing/charge-types returns registered charge types."""
    from openfmis.plugin_sdk.hooks import (
        _clear_all_registries,
        register_plugin,
    )
    from openfmis.plugin_sdk.manifest import ChargeType, PluginManifest

    _clear_all_registries()

    manifest = PluginManifest(
        slug="api-ct-test",
        name="API CT Test",
        version="1.0.0",
        charge_types=[
            ChargeType(operation="api.ct.op", description="API test op"),
        ],
    )
    register_plugin(manifest)

    token = await _login(client, "billadmin", "adminpassword123")
    resp = await client.get(
        "/api/v1/billing/charge-types",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    ops = {ct["operation"] for ct in data}
    assert "api.ct.op" in ops

    _clear_all_registries()


@pytest.mark.asyncio
async def test_price_item_includes_module_id(
    client: AsyncClient, db_session: AsyncSession, admin_user: User
):
    """Price catalog entries include module_id in API response."""
    from openfmis.plugin_sdk.manifest import ChargeType, PluginManifest

    manifest = PluginManifest(
        slug="price-mod-test",
        name="Price Module Test",
        version="1.0.0",
        charge_types=[
            ChargeType(operation="price.mod.test", description="Test"),
        ],
    )
    svc = PricingService(db_session)
    await svc.sync_charge_types(manifest)
    await db_session.flush()

    token = await _login(client, "billadmin", "adminpassword123")
    resp = await client.get(
        "/api/v1/billing/prices/price.mod.test",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["module_id"] == "price-mod-test"


# ── Cross-account transactions endpoint tests ──────────────────────────────


@pytest.mark.asyncio
async def test_transactions_returns_all_entries(
    client: AsyncClient, db_session: AsyncSession, admin_user: User, regular_user: User
):
    """GET /billing/transactions returns entries across accounts."""
    svc = CreditAccountingService(db_session)
    await svc.add_credits("user", regular_user.id, CreditAdd(amount=100, reference="txn-test"))
    await svc.add_credits("user", admin_user.id, CreditAdd(amount=200, reference="txn-test-admin"))
    await db_session.flush()

    token = await _login(client, "billadmin", "adminpassword123")
    resp = await client.get(
        "/api/v1/billing/transactions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2
    # Each item should have owner_type and owner_id
    for item in data["items"]:
        assert "owner_type" in item
        assert "owner_id" in item
        assert "entry_type" in item


@pytest.mark.asyncio
async def test_transactions_filter_by_entry_type(
    client: AsyncClient, db_session: AsyncSession, admin_user: User, regular_user: User
):
    """Transactions can be filtered by entry_type."""
    svc = CreditAccountingService(db_session)
    await svc.add_credits("user", regular_user.id, CreditAdd(amount=500, reference="filter-type"))
    await svc.consume_credits(
        "user",
        regular_user.id,
        CreditConsume(amount=50, reference="filter-type"),
    )
    await db_session.flush()

    token = await _login(client, "billadmin", "adminpassword123")
    resp = await client.get(
        "/api/v1/billing/transactions?entry_type=consume",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    for item in data["items"]:
        assert item["entry_type"] == "consume"


@pytest.mark.asyncio
async def test_transactions_filter_by_owner_type(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    regular_user: User,
    billing_group,
):
    """Transactions can be filtered by owner_type."""
    svc = CreditAccountingService(db_session)
    await svc.add_credits("user", regular_user.id, CreditAdd(amount=100, reference="ot-user"))
    await svc.add_credits("group", billing_group.id, CreditAdd(amount=200, reference="ot-group"))
    await db_session.flush()

    token = await _login(client, "billadmin", "adminpassword123")
    resp = await client.get(
        "/api/v1/billing/transactions?owner_type=group",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    for item in data["items"]:
        assert item["owner_type"] == "group"


@pytest.mark.asyncio
async def test_transactions_requires_superuser(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, billing_group
):
    """Non-superusers cannot access cross-account transactions."""
    token = await _login(client, "billuser", "testpassword123")
    resp = await client.get(
        "/api/v1/billing/transactions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_transactions_pagination(
    client: AsyncClient, db_session: AsyncSession, admin_user: User, regular_user: User
):
    """Transactions endpoint supports pagination."""
    svc = CreditAccountingService(db_session)
    await svc.add_credits("user", regular_user.id, CreditAdd(amount=1000, reference="page-test"))
    for i in range(5):
        await svc.consume_credits(
            "user",
            regular_user.id,
            CreditConsume(amount=10, reference=f"page-{i}"),
        )
    await db_session.flush()

    token = await _login(client, "billadmin", "adminpassword123")
    resp = await client.get(
        "/api/v1/billing/transactions?limit=2&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) <= 2
    assert data["total"] >= 6  # 1 add + 5 consumes
    assert data["offset"] == 0
    assert data["limit"] == 2


@pytest.mark.asyncio
async def test_transactions_service_method(
    db_session: AsyncSession, regular_user: User, billing_group
):
    """Service-level test for get_transactions."""
    svc = CreditAccountingService(db_session)
    await svc.add_credits("user", regular_user.id, CreditAdd(amount=100, reference="svc-txn"))
    await svc.add_credits("group", billing_group.id, CreditAdd(amount=200, reference="svc-txn-grp"))
    await db_session.flush()

    items, total = await svc.get_transactions()
    assert total >= 2
    owner_types = {item["owner_type"] for item in items}
    assert "user" in owner_types
    assert "group" in owner_types
    for item in items:
        assert "entry" in item
        assert "owner_id" in item
