"""Preference endpoints — per-user settings."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.schemas.preference import PreferenceList, PreferenceRead, PreferenceUpsert
from openfmis.services.preference import PreferenceService

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("", response_model=PreferenceList)
async def list_preferences(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PreferenceList:
    svc = PreferenceService(db)
    prefs = await svc.list_for_user(current_user.id)
    return PreferenceList(items=[PreferenceRead.model_validate(p) for p in prefs])


@router.get("/{namespace}", response_model=PreferenceRead)
async def get_preference(
    namespace: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PreferenceRead:
    svc = PreferenceService(db)
    pref = await svc.get(current_user.id, namespace)
    return PreferenceRead.model_validate(pref)


@router.put("", response_model=PreferenceRead)
async def upsert_preference(
    body: PreferenceUpsert,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PreferenceRead:
    svc = PreferenceService(db)
    pref = await svc.upsert(current_user.id, body)
    return PreferenceRead.model_validate(pref)


@router.delete("/{namespace}", status_code=204)
async def delete_preference(
    namespace: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    svc = PreferenceService(db)
    await svc.delete(current_user.id, namespace)
