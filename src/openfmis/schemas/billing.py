"""Pydantic schemas for billing (credit accounts, ledger, prices)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

OwnerType = Literal["user", "group"]
EntryType = Literal["purchase", "consume", "refund", "adjustment"]


# ── Credit Account ────────────────────────────────────────────────────────────


class CreditAccountOut(BaseModel):
    id: uuid.UUID
    owner_type: OwnerType
    owner_id: uuid.UUID
    balance: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Ledger ────────────────────────────────────────────────────────────────────


class LedgerEntryOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    entry_type: EntryType
    amount: int
    balance_after: int
    reference: str | None
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class LedgerPage(BaseModel):
    items: list[LedgerEntryOut]
    total: int
    offset: int
    limit: int


# ── Credit operations ─────────────────────────────────────────────────────────


class CreditAdd(BaseModel):
    amount: int = Field(..., gt=0, description="Credits to add (must be positive)")
    reference: str | None = Field(None, max_length=255)
    note: str | None = None


class CreditConsume(BaseModel):
    amount: int = Field(..., gt=0, description="Credits to consume (must be positive)")
    reference: str | None = Field(None, max_length=255)
    note: str | None = None


class CreditRefund(BaseModel):
    amount: int = Field(..., gt=0, description="Credits to refund (must be positive)")
    reference: str | None = Field(None, max_length=255)
    note: str | None = None


# ── Price catalog ─────────────────────────────────────────────────────────────


class PriceItemOut(BaseModel):
    id: int
    operation: str
    credit_cost: int
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PriceSet(BaseModel):
    credit_cost: int = Field(..., ge=0)
    description: str | None = None
    is_active: bool = True
