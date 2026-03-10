"""Scene notification endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.schemas.notification import (
    MarkViewedRequest,
    NotificationOut,
    NotificationPreferenceOut,
    NotificationPreferenceUpdate,
    SetVisibilityRequest,
)
from openfmis.services.scene_notification import SceneNotificationService

router = APIRouter(prefix="/satshot/notifications", tags=["satshot-notifications"])


@router.get("/", response_model=dict)
async def list_notifications(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    unread_only: bool = False,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    svc = SceneNotificationService(db)
    items, total = await svc.list_for_user(
        current_user.id, unread_only=unread_only, limit=limit, offset=offset
    )
    return {
        "items": [NotificationOut.model_validate(n).model_dump() for n in items],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.post("/viewed", response_model=dict)
async def mark_viewed(
    data: MarkViewedRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    svc = SceneNotificationService(db)
    count = await svc.mark_viewed(data.notification_ids)
    await db.commit()
    return {"updated": count}


@router.post("/visibility", response_model=dict)
async def set_visibility(
    data: SetVisibilityRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    svc = SceneNotificationService(db)
    count = await svc.set_visibility(data.notification_ids, data.visible)
    await db.commit()
    return {"updated": count}


@router.get("/preferences", response_model=NotificationPreferenceOut | None)
async def get_preferences(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    svc = SceneNotificationService(db)
    pref = await svc.get_preferences(current_user.id)
    if pref is None:
        return None
    return NotificationPreferenceOut.model_validate(pref)


@router.put("/preferences", response_model=NotificationPreferenceOut)
async def update_preferences(
    data: NotificationPreferenceUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> NotificationPreferenceOut:
    svc = SceneNotificationService(db)
    pref = await svc.set_preferences(
        current_user.id,
        email_enabled=data.email_enabled,
        scene_types=data.scene_types,
        settings=data.settings,
    )
    await db.commit()
    return NotificationPreferenceOut.model_validate(pref)


@router.delete("/preferences", status_code=status.HTTP_204_NO_CONTENT)
async def clear_preferences(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    svc = SceneNotificationService(db)
    await svc.clear_preferences(current_user.id)
    await db.commit()
