"""Logo endpoints — per-group branding."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.schemas.logo import LogoRead, LogoUpsert
from openfmis.services.logo import LogoService

router = APIRouter(prefix="/logos", tags=["logos"])


@router.get("/{group_id}", response_model=LogoRead)
async def get_logo(
    group_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> LogoRead:
    svc = LogoService(db)
    logo = await svc.get_by_group(group_id)
    return LogoRead.model_validate(logo)


@router.put("", response_model=LogoRead)
async def upsert_logo(
    body: LogoUpsert,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> LogoRead:
    svc = LogoService(db)
    logo = await svc.upsert(body)
    return LogoRead.model_validate(logo)


@router.delete("/{group_id}", status_code=204)
async def delete_logo(
    group_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    svc = LogoService(db)
    await svc.delete(group_id)
