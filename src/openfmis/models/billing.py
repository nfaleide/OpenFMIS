"""Billing models — credit accounts, ledger, and price catalog."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openfmis.models.base import Base


class CreditAccount(Base):
    __tablename__ = "credit_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_type: Mapped[str] = mapped_column(String(10), nullable=False)  # "user" | "group"
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    balance: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    entries: Mapped[list["LedgerEntry"]] = relationship(
        "LedgerEntry", back_populates="account", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("owner_type", "owner_id", name="uq_credit_account_owner"),
        CheckConstraint("owner_type IN ('user', 'group')", name="ck_credit_account_owner_type"),
        CheckConstraint("balance >= 0", name="ck_credit_account_balance_nonneg"),
        Index("idx_credit_accounts_owner", "owner_type", "owner_id"),
    )

    def __repr__(self) -> str:
        return f"<CreditAccount {self.owner_type}:{self.owner_id} balance={self.balance}>"


class LedgerEntry(Base):
    __tablename__ = "credit_ledger"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("credit_accounts.id", ondelete="CASCADE"), nullable=False
    )
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    account: Mapped["CreditAccount"] = relationship("CreditAccount", back_populates="entries")

    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('purchase', 'consume', 'refund', 'adjustment')",
            name="ck_ledger_entry_type",
        ),
        Index("idx_credit_ledger_account", "account_id"),
        Index("idx_credit_ledger_account_created", "account_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<LedgerEntry {self.entry_type} {self.amount:+d}>"


class PriceItem(Base):
    __tablename__ = "price_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    credit_cost: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("credit_cost >= 0", name="ck_price_catalog_cost_nonneg"),
        Index("idx_price_catalog_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<PriceItem {self.operation}={self.credit_cost}>"
