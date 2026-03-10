"""Billing API — credit accounts, ledger history, and price catalog."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user, get_superuser
from openfmis.models.user import User
from openfmis.schemas.billing import (
    CreditAccountOut,
    CreditAdd,
    CreditConsume,
    CreditRefund,
    LedgerEntryOut,
    LedgerPage,
    PriceItemOut,
    PriceSet,
)
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


# ── Account endpoints ─────────────────────────────────────────────────────────


@router.get("/accounts/{owner_type}/{owner_id}", response_model=CreditAccountOut)
async def get_account(
    owner_type: OwnerTypeLiteral,
    owner_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CreditAccountOut:
    _check_owner_access(current_user, owner_type, owner_id)
    svc = CreditAccountingService(db)
    account = await svc.get_or_create_account(owner_type, owner_id)
    await db.commit()
    return CreditAccountOut.model_validate(account)


@router.get("/accounts/{owner_type}/{owner_id}/ledger", response_model=LedgerPage)
async def get_ledger(
    owner_type: OwnerTypeLiteral,
    owner_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> LedgerPage:
    _check_owner_access(current_user, owner_type, owner_id)
    svc = CreditAccountingService(db)
    entries, total = await svc.get_ledger(owner_type, owner_id, offset=offset, limit=limit)
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
)
async def consume_credits(
    owner_type: OwnerTypeLiteral,
    owner_id: uuid.UUID,
    data: CreditConsume,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> LedgerEntryOut:
    """Consume credits from an account (authenticated users for their own account)."""
    _check_owner_access(current_user, owner_type, owner_id)
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


# ── Price catalog endpoints ───────────────────────────────────────────────────


@router.get("/prices", response_model=list[PriceItemOut])
async def list_prices(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    active_only: bool = True,
) -> list[PriceItemOut]:
    svc = PricingService(db)
    items = await svc.list_prices(active_only=active_only or not current_user.is_superuser)
    return [PriceItemOut.model_validate(i) for i in items]


@router.get("/prices/{operation}", response_model=PriceItemOut)
async def get_price(
    operation: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PriceItemOut:
    svc = PricingService(db)
    item = await svc.get_price(operation)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operation not found")
    return PriceItemOut.model_validate(item)


@router.put("/prices/{operation}", response_model=PriceItemOut)
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


@router.delete("/prices/{operation}", status_code=status.HTTP_204_NO_CONTENT)
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operation not found")
