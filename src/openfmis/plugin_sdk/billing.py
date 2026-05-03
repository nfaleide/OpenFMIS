"""Plugin SDK — Billing contract.

Plugins record charges and query balances through these functions.
Direct writes to the credit_ledger table are forbidden outside
services/billing.py.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.schemas.billing import CreditConsume
from openfmis.services.billing import CreditAccountingService


async def record_charge(
    db: AsyncSession,
    owner_type: str,
    owner_id: UUID,
    operation: str,
    amount: int,
    reference: str | None = None,
    note: str | None = None,
) -> None:
    """Consume *amount* credits from the owner's account.

    Raises ``InsufficientCreditsError`` if balance is too low.
    """
    svc = CreditAccountingService(db)
    await svc.consume_credits(
        owner_type,
        owner_id,
        CreditConsume(amount=amount, reference=reference or operation, note=note),
    )


async def get_balance(db: AsyncSession, owner_type: str, owner_id: UUID) -> int:
    """Return the current credit balance (0 if no account exists)."""
    svc = CreditAccountingService(db)
    account = await svc.get_account(owner_type, owner_id)
    if account is None:
        return 0
    return account.balance


async def has_sufficient_balance(
    db: AsyncSession,
    owner_type: str,
    owner_id: UUID,
    amount: int,
) -> bool:
    """Return True if the owner has at least *amount* credits."""
    bal = await get_balance(db, owner_type, owner_id)
    return bal >= amount
