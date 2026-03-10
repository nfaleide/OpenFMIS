"""Billing services — CreditAccountingService and PricingService."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.billing import CreditAccount, LedgerEntry, PriceItem
from openfmis.schemas.billing import CreditAdd, CreditConsume, CreditRefund, PriceSet


class InsufficientCreditsError(Exception):
    """Raised when an account has insufficient credits for a consume operation."""

    def __init__(self, balance: int, requested: int) -> None:
        self.balance = balance
        self.requested = requested
        super().__init__(f"Insufficient credits: have {balance}, need {requested}")


class AccountNotFoundError(Exception):
    pass


class OperationNotFoundError(Exception):
    pass


# ── CreditAccountingService ───────────────────────────────────────────────────


class CreditAccountingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_or_create_account(self, owner_type: str, owner_id: uuid.UUID) -> CreditAccount:
        """Return the credit account for owner, creating one if it doesn't exist."""
        result = await self.db.execute(
            select(CreditAccount).where(
                CreditAccount.owner_type == owner_type,
                CreditAccount.owner_id == owner_id,
            )
        )
        account = result.scalar_one_or_none()
        if account is None:
            account = CreditAccount(owner_type=owner_type, owner_id=owner_id, balance=0)
            self.db.add(account)
            try:
                await self.db.flush()
            except IntegrityError:
                await self.db.rollback()
                # Race — another request created it; fetch
                result = await self.db.execute(
                    select(CreditAccount).where(
                        CreditAccount.owner_type == owner_type,
                        CreditAccount.owner_id == owner_id,
                    )
                )
                account = result.scalar_one()
            await self.db.refresh(account)
        return account

    async def get_account(self, owner_type: str, owner_id: uuid.UUID) -> CreditAccount | None:
        result = await self.db.execute(
            select(CreditAccount).where(
                CreditAccount.owner_type == owner_type,
                CreditAccount.owner_id == owner_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_account_by_id(self, account_id: uuid.UUID) -> CreditAccount | None:
        result = await self.db.execute(select(CreditAccount).where(CreditAccount.id == account_id))
        return result.scalar_one_or_none()

    async def add_credits(
        self,
        owner_type: str,
        owner_id: uuid.UUID,
        data: CreditAdd,
    ) -> LedgerEntry:
        account = await self.get_or_create_account(owner_type, owner_id)
        account.balance += data.amount
        entry = LedgerEntry(
            account_id=account.id,
            entry_type="purchase",
            amount=data.amount,
            balance_after=account.balance,
            reference=data.reference,
            note=data.note,
        )
        self.db.add(entry)
        await self.db.flush()
        await self.db.refresh(entry)
        await self.db.refresh(account)
        return entry

    async def consume_credits(
        self,
        owner_type: str,
        owner_id: uuid.UUID,
        data: CreditConsume,
    ) -> LedgerEntry:
        account = await self.get_or_create_account(owner_type, owner_id)
        if account.balance < data.amount:
            raise InsufficientCreditsError(account.balance, data.amount)
        account.balance -= data.amount
        entry = LedgerEntry(
            account_id=account.id,
            entry_type="consume",
            amount=-data.amount,
            balance_after=account.balance,
            reference=data.reference,
            note=data.note,
        )
        self.db.add(entry)
        await self.db.flush()
        await self.db.refresh(entry)
        await self.db.refresh(account)
        return entry

    async def refund_credits(
        self,
        owner_type: str,
        owner_id: uuid.UUID,
        data: CreditRefund,
    ) -> LedgerEntry:
        account = await self.get_or_create_account(owner_type, owner_id)
        account.balance += data.amount
        entry = LedgerEntry(
            account_id=account.id,
            entry_type="refund",
            amount=data.amount,
            balance_after=account.balance,
            reference=data.reference,
            note=data.note,
        )
        self.db.add(entry)
        await self.db.flush()
        await self.db.refresh(entry)
        await self.db.refresh(account)
        return entry

    async def get_ledger(
        self,
        owner_type: str,
        owner_id: uuid.UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[LedgerEntry], int]:
        account = await self.get_account(owner_type, owner_id)
        if account is None:
            return [], 0

        count_result = await self.db.execute(
            select(func.count())
            .select_from(LedgerEntry)
            .where(LedgerEntry.account_id == account.id)
        )
        total = count_result.scalar_one()

        result = await self.db.execute(
            select(LedgerEntry)
            .where(LedgerEntry.account_id == account.id)
            .order_by(LedgerEntry.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total


# ── PricingService ────────────────────────────────────────────────────────────


class PricingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_prices(self, active_only: bool = True) -> list[PriceItem]:
        stmt = select(PriceItem).order_by(PriceItem.operation)
        if active_only:
            stmt = stmt.where(PriceItem.is_active.is_(True))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_price(self, operation: str) -> PriceItem | None:
        result = await self.db.execute(select(PriceItem).where(PriceItem.operation == operation))
        return result.scalar_one_or_none()

    async def get_credit_cost(self, operation: str) -> int:
        """Return the credit cost for an operation. Returns 0 if not found or inactive."""
        item = await self.get_price(operation)
        if item is None or not item.is_active:
            return 0
        return item.credit_cost

    async def set_price(self, operation: str, data: PriceSet) -> PriceItem:
        """Upsert a price catalog entry."""
        item = await self.get_price(operation)
        if item is None:
            item = PriceItem(operation=operation)
            self.db.add(item)
        item.credit_cost = data.credit_cost
        item.is_active = data.is_active
        if data.description is not None:
            item.description = data.description
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def deactivate(self, operation: str) -> PriceItem:
        item = await self.get_price(operation)
        if item is None:
            raise OperationNotFoundError(operation)
        item.is_active = False
        await self.db.flush()
        await self.db.refresh(item)
        return item
