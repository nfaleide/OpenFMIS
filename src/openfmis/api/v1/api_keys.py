"""API key endpoints — create, list, revoke long-lived bearer tokens."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.services.api_key import APIKeyService

router = APIRouter(prefix="/auth/api-keys", tags=["auth"])


class APIKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    expires_at: datetime | None = None
    note: str | None = None


class APIKeyCreateResponse(BaseModel):
    id: UUID
    name: str
    key_prefix: str
    raw_key: str  # Only returned at creation time
    expires_at: datetime | None
    created_at: datetime


class APIKeyRead(BaseModel):
    id: UUID
    name: str
    key_prefix: str
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.post("", response_model=APIKeyCreateResponse, status_code=201, summary="Create api key")
async def create_api_key(
    body: APIKeyCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> APIKeyCreateResponse:
    """Create a new API key for the current user."""
    svc = APIKeyService(db)
    key, raw_key = await svc.create_key(
        user_id=current_user.id,
        name=body.name,
        expires_at=body.expires_at,
        note=body.note,
    )
    return APIKeyCreateResponse(
        id=key.id,
        name=key.name,
        key_prefix=key.key_prefix,
        raw_key=raw_key,
        expires_at=key.expires_at,
        created_at=key.created_at,
    )


@router.get("", response_model=list[APIKeyRead], summary="List api keys")
async def list_api_keys(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    include_revoked: bool = False,
) -> list[APIKeyRead]:
    """List API keys for the current user."""
    svc = APIKeyService(db)
    keys = await svc.list_keys(current_user.id, include_revoked=include_revoked)
    return [APIKeyRead.model_validate(k) for k in keys]


@router.delete("/{key_id}", response_model=APIKeyRead, summary="Revoke api key")
async def revoke_api_key(
    key_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> APIKeyRead:
    """Revoke an API key."""
    svc = APIKeyService(db)
    key = await svc.revoke_key(key_id, current_user.id)
    return APIKeyRead.model_validate(key)
