"""Billing services — CreditAccountingService and PricingService."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.billing import CreditAccount, LedgerEntry, PriceItem
from openfmis.plugin_sdk.manifest import PluginManifest
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

    async def reconcile(
        self,
        owner_type: str,
        owner_id: uuid.UUID,
    ) -> tuple[int, int, bool]:
        """Reconcile cached balance against ledger SUM.

        Returns (cached_balance, derived_balance, is_consistent).
        If inconsistent, updates the cached balance to match the ledger.
        """
        account = await self.get_account(owner_type, owner_id)
        if account is None:
            return 0, 0, True

        result = await self.db.execute(
            select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
                LedgerEntry.account_id == account.id
            )
        )
        derived = int(result.scalar_one())
        cached = account.balance
        consistent = cached == derived

        if not consistent:
            account.balance = derived
            await self.db.flush()

        return cached, derived, consistent

    async def get_ledger(
        self,
        owner_type: str,
        owner_id: uuid.UUID,
        offset: int = 0,
        limit: int = 50,
        entry_type: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        reference_contains: str | None = None,
    ) -> tuple[list[LedgerEntry], int]:
        account = await self.get_account(owner_type, owner_id)
        if account is None:
            return [], 0

        filters = [LedgerEntry.account_id == account.id]
        if entry_type is not None:
            filters.append(LedgerEntry.entry_type == entry_type)
        if date_from is not None:
            filters.append(LedgerEntry.created_at >= date_from)
        if date_to is not None:
            filters.append(LedgerEntry.created_at <= date_to)
        if reference_contains is not None:
            filters.append(LedgerEntry.reference.ilike(f"%{reference_contains}%"))

        count_result = await self.db.execute(
            select(func.count()).select_from(LedgerEntry).where(*filters)
        )
        total = count_result.scalar_one()

        result = await self.db.execute(
            select(LedgerEntry)
            .where(*filters)
            .order_by(LedgerEntry.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_transactions(
        self,
        offset: int = 0,
        limit: int = 50,
        entry_type: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        reference_contains: str | None = None,
        module_id: str | None = None,
        owner_type: str | None = None,
    ) -> tuple[list[dict], int]:
        """Return ledger entries across all accounts with optional filters.

        Each result dict includes the entry plus owner_type/owner_id from the account.
        """
        base_join = select(
            LedgerEntry,
            CreditAccount.owner_type,
            CreditAccount.owner_id,
        ).join(CreditAccount, LedgerEntry.account_id == CreditAccount.id)

        filters = []
        if entry_type is not None:
            filters.append(LedgerEntry.entry_type == entry_type)
        if date_from is not None:
            filters.append(LedgerEntry.created_at >= date_from)
        if date_to is not None:
            filters.append(LedgerEntry.created_at <= date_to)
        if reference_contains is not None:
            filters.append(LedgerEntry.reference.ilike(f"%{reference_contains}%"))
        if module_id is not None:
            filters.append(LedgerEntry.reference.ilike(f"%{module_id}%"))
        if owner_type is not None:
            filters.append(CreditAccount.owner_type == owner_type)

        count_q = (
            select(func.count())
            .select_from(LedgerEntry)
            .join(CreditAccount, LedgerEntry.account_id == CreditAccount.id)
        )
        if filters:
            count_q = count_q.where(*filters)
        total = (await self.db.execute(count_q)).scalar_one()

        q = base_join
        if filters:
            q = q.where(*filters)
        q = q.order_by(LedgerEntry.created_at.desc()).offset(offset).limit(limit)

        result = await self.db.execute(q)
        items = []
        for entry, ot, oid in result.all():
            items.append(
                {
                    "entry": entry,
                    "owner_type": ot,
                    "owner_id": oid,
                }
            )
        return items, total

    async def get_balances_batch(
        self,
        owner_type: str,
        owner_ids: list[uuid.UUID],
    ) -> list[dict]:
        """Return balances for multiple owners in a single query."""
        if not owner_ids:
            return []
        result = await self.db.execute(
            select(CreditAccount.owner_id, CreditAccount.balance).where(
                CreditAccount.owner_type == owner_type,
                CreditAccount.owner_id.in_(owner_ids),
            )
        )
        found = {row[0]: row[1] for row in result.all()}
        return [{"owner_id": oid, "balance": found.get(oid, 0)} for oid in owner_ids]


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

    async def sync_charge_types(self, manifest: PluginManifest) -> int:
        """Upsert charge types from a plugin manifest into the price catalog.

        Creates entries with credit_cost=0 (admin sets prices later).
        Updates description and module_id for existing entries.
        Returns count of new entries created.
        """
        created = 0
        for ct in manifest.charge_types:
            item = await self.get_price(ct.operation)
            if item is None:
                item = PriceItem(
                    operation=ct.operation,
                    credit_cost=0,
                    description=ct.description,
                    module_id=manifest.slug,
                )
                self.db.add(item)
                created += 1
            else:
                if ct.description:
                    item.description = ct.description
                item.module_id = manifest.slug
        if created:
            await self.db.flush()
        return created

    async def list_by_module(self, module_id: str) -> list[PriceItem]:
        """List all price items registered by a specific plugin."""
        result = await self.db.execute(
            select(PriceItem).where(PriceItem.module_id == module_id).order_by(PriceItem.operation)
        )
        return list(result.scalars().all())
