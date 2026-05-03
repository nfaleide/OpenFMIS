"""Billing API — credit accounts, ledger history, and price catalog.

ACL enforcement:
- view_financials: required for balance read and ledger history
- make_payments: required for consuming credits
- Price catalog writes: superuser only
- add_credits / refund: superuser only
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user, get_superuser
from openfmis.exceptions import AuthorizationError
from openfmis.models.user import User
from openfmis.plugin_sdk.hooks import list_charge_types
from openfmis.schemas.billing import (
    CreditAccountOut,
    CreditAdd,
    CreditConsume,
    CreditRefund,
    LedgerEntryOut,
    LedgerPage,
    PriceItemOut,
    PriceSet,
    TransactionOut,
    TransactionPage,
)
from openfmis.services.acl import ACLService
from openfmis.services.billing import (
    CreditAccountingService,
    InsufficientCreditsError,
    OperationNotFoundError,
    PricingService,
)

router = APIRouter(prefix="/billing", tags=["billing"])

OwnerTypeLiteral = Literal["user", "group"]


def _check_owner_access(current_user: User, owner_type: str, owner_id: uuid.UUID) -> None:
    """Non-superusers can only access their own user account."""
    if current_user.is_superuser:
        return
    if owner_type == "user" and owner_id == current_user.id:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


async def _check_billing_permission(
    db: AsyncSession,
    user: User,
    permission: str,
) -> None:
    """Check a billing permission (view_financials / make_payments)."""
    acl = ACLService(db)
    allowed = await acl.check_permission(user, permission, "billing")
    if not allowed:
        raise AuthorizationError(f"Permission '{permission}' denied on 'billing'")


# ── Account endpoints ───────────────���─────────────────────────────���───────────


@router.get(
    "/accounts/{owner_type}/{owner_id}",
    response_model=CreditAccountOut,
    summary="Get account",
)
async def get_account(
    owner_type: OwnerTypeLiteral,
    owner_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CreditAccountOut:
    _check_owner_access(current_user, owner_type, owner_id)
    await _check_billing_permission(db, current_user, "view_financials")
    svc = CreditAccountingService(db)
    account = await svc.get_or_create_account(owner_type, owner_id)
    await db.commit()
    return CreditAccountOut.model_validate(account)


@router.get(
    "/accounts/{owner_type}/{owner_id}/ledger",
    response_model=LedgerPage,
    summary="Get ledger",
)
async def get_ledger(
    owner_type: OwnerTypeLiteral,
    owner_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    entry_type: str | None = Query(None, description="Filter by entry type"),
    date_from: datetime | None = Query(None, description="Filter entries after this date"),
    date_to: datetime | None = Query(None, description="Filter entries before this date"),
    reference: str | None = Query(None, description="Search within reference field"),
) -> LedgerPage:
    _check_owner_access(current_user, owner_type, owner_id)
    await _check_billing_permission(db, current_user, "view_financials")
    svc = CreditAccountingService(db)
    entries, total = await svc.get_ledger(
        owner_type,
        owner_id,
        offset=offset,
        limit=limit,
        entry_type=entry_type,
        date_from=date_from,
        date_to=date_to,
        reference_contains=reference,
    )
    return LedgerPage(
        items=[LedgerEntryOut.model_validate(e) for e in entries],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post(
    "/accounts/{owner_type}/{owner_id}/credits",
    response_model=LedgerEntryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add credits",
)
async def add_credits(
    owner_type: OwnerTypeLiteral,
    owner_id: uuid.UUID,
    data: CreditAdd,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_superuser)],
) -> LedgerEntryOut:
    """Add credits to an account. Superuser only."""
    svc = CreditAccountingService(db)
    entry = await svc.add_credits(owner_type, owner_id, data)
    await db.commit()
    return LedgerEntryOut.model_validate(entry)


@router.post(
    "/accounts/{owner_type}/{owner_id}/consume",
    response_model=LedgerEntryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Consume credits",
)
async def consume_credits(
    owner_type: OwnerTypeLiteral,
    owner_id: uuid.UUID,
    data: CreditConsume,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> LedgerEntryOut:
    """Consume credits from an account."""
    _check_owner_access(current_user, owner_type, owner_id)
    await _check_billing_permission(db, current_user, "make_payments")
    svc = CreditAccountingService(db)
    try:
        entry = await svc.consume_credits(owner_type, owner_id, data)
        await db.commit()
    except InsufficientCreditsError as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits: balance={exc.balance}, required={exc.requested}",
        )
    return LedgerEntryOut.model_validate(entry)


@router.post(
    "/accounts/{owner_type}/{owner_id}/refund",
    response_model=LedgerEntryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Refund credits",
)
async def refund_credits(
    owner_type: OwnerTypeLiteral,
    owner_id: uuid.UUID,
    data: CreditRefund,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_superuser)],
) -> LedgerEntryOut:
    """Refund credits to an account. Superuser only."""
    svc = CreditAccountingService(db)
    entry = await svc.refund_credits(owner_type, owner_id, data)
    await db.commit()
    return LedgerEntryOut.model_validate(entry)


@router.post("/accounts/{owner_type}/{owner_id}/reconcile", summary="Reconcile account")
async def reconcile_account(
    owner_type: OwnerTypeLiteral,
    owner_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_superuser)],
) -> dict:
    """Reconcile cached balance against ledger SUM. Superuser only.

    If inconsistent, auto-corrects the cached balance.
    """
    svc = CreditAccountingService(db)
    cached, derived, consistent = await svc.reconcile(owner_type, owner_id)
    if not consistent:
        await db.commit()
    return {
        "cached_balance": cached,
        "derived_balance": derived,
        "consistent": consistent,
        "corrected": not consistent,
    }


# ── Cross-account transactions (admin) ──────────────────────────────────────


@router.get("/transactions", response_model=TransactionPage, summary="Get transactions")
async def get_transactions(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_superuser)],
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    entry_type: str | None = Query(None, description="Filter by entry type"),
    date_from: datetime | None = Query(None, description="Filter entries after this date"),
    date_to: datetime | None = Query(None, description="Filter entries before this date"),
    reference: str | None = Query(None, description="Search within reference field"),
    module_id: str | None = Query(None, description="Filter by plugin module"),
    owner_type: OwnerTypeLiteral | None = Query(None, description="Filter by owner type"),
) -> TransactionPage:
    """List ledger entries across all accounts. Superuser only."""
    svc = CreditAccountingService(db)
    items, total = await svc.get_transactions(
        offset=offset,
        limit=limit,
        entry_type=entry_type,
        date_from=date_from,
        date_to=date_to,
        reference_contains=reference,
        module_id=module_id,
        owner_type=owner_type,
    )
    return TransactionPage(
        items=[
            TransactionOut(
                **LedgerEntryOut.model_validate(item["entry"]).model_dump(),
                owner_type=item["owner_type"],
                owner_id=item["owner_id"],
            )
            for item in items
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


# ── Batch balances endpoint ────────��─────────────────────────────────────────


class BatchBalanceRequest(BaseModel):
    owner_type: OwnerTypeLiteral
    owner_ids: list[uuid.UUID]


class BalanceItem(BaseModel):
    owner_id: uuid.UUID
    balance: int


@router.post("/balances", response_model=list[BalanceItem], summary="Get balances batch")
async def get_balances_batch(
    body: BatchBalanceRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_superuser)],
) -> list[BalanceItem]:
    """Return balances for multiple owners. Superuser / admin-dealer view."""
    svc = CreditAccountingService(db)
    results = await svc.get_balances_batch(body.owner_type, body.owner_ids)
    return [BalanceItem(**r) for r in results]


# ── Price catalog endpoints ─────────────────��────────────────────────────────


@router.get("/prices", response_model=list[PriceItemOut], summary="List prices")
async def list_prices(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    active_only: bool = True,
) -> list[PriceItemOut]:
    await _check_billing_permission(db, current_user, "view_financials")
    svc = PricingService(db)
    items = await svc.list_prices(active_only=active_only or not current_user.is_superuser)
    return [PriceItemOut.model_validate(i) for i in items]


@router.get("/prices/{operation}", response_model=PriceItemOut, summary="Get price")
async def get_price(
    operation: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PriceItemOut:
    await _check_billing_permission(db, current_user, "view_financials")
    svc = PricingService(db)
    item = await svc.get_price(operation)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operation not found")
    return PriceItemOut.model_validate(item)


@router.put("/prices/{operation}", response_model=PriceItemOut, summary="Set price")
async def set_price(
    operation: str,
    data: PriceSet,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_superuser)],
) -> PriceItemOut:
    """Upsert a price catalog entry. Superuser only."""
    svc = PricingService(db)
    item = await svc.set_price(operation, data)
    await db.commit()
    return PriceItemOut.model_validate(item)


@router.delete(
    "/prices/{operation}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate price",
)
async def deactivate_price(
    operation: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_superuser)],
) -> None:
    """Deactivate a price catalog entry. Superuser only."""
    svc = PricingService(db)
    try:
        await svc.deactivate(operation)
        await db.commit()
    except OperationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Operation not found",
        )


# ── Charge type registry endpoint ────────────────────────────────────────────


class ChargeTypeOut(BaseModel):
    operation: str
    plugin_slug: str
    description: str


@router.get("/charge-types", response_model=list[ChargeTypeOut], summary="Get charge types")
async def get_charge_types(
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ChargeTypeOut]:
    """List all charge types registered by plugins (in-memory registry)."""
    return [
        ChargeTypeOut(
            operation=ct.operation,
            plugin_slug=ct.plugin_slug,
            description=ct.description,
        )
        for ct in list_charge_types()
    ]
