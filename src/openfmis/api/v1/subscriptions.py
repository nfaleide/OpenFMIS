"""Subscription lifecycle endpoints — start, renew, cancel, expire."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user, get_superuser
from openfmis.models.user import User
from openfmis.schemas.subscription import (
    SubscriptionCancel,
    SubscriptionCreate,
    SubscriptionOut,
    SubscriptionRenew,
)
from openfmis.services.subscription import (
    SubscriptionNotFoundError,
    SubscriptionService,
)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.post(
    "",
    response_model=SubscriptionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Start subscription",
)
async def start_subscription(
    body: SubscriptionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SubscriptionOut:
    """Create a new subscription."""
    svc = SubscriptionService(db)
    sub = await svc.start(
        owner_type=body.owner_type,
        owner_id=body.owner_id,
        plugin_id=body.plugin_id,
        subscription_type=body.subscription_type,
        expires_at=body.expires_at,
        metadata=body.metadata,
    )
    await db.commit()
    return SubscriptionOut.model_validate(sub)


@router.get("/{subscription_id}", response_model=SubscriptionOut, summary="Get subscription")
async def get_subscription(
    subscription_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SubscriptionOut:
    svc = SubscriptionService(db)
    try:
        sub = await svc.get(subscription_id)
    except SubscriptionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    return SubscriptionOut.model_validate(sub)


@router.get("", response_model=dict, summary="List subscriptions")
async def list_subscriptions(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    owner_type: str = "user",
    owner_id: uuid.UUID | None = None,
    sub_status: str | None = Query(None, alias="status"),
    plugin_id: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """List subscriptions for an owner."""
    oid = owner_id or current_user.id
    svc = SubscriptionService(db)
    items, total = await svc.list_for_owner(
        owner_type=owner_type,
        owner_id=oid,
        status=sub_status,
        plugin_id=plugin_id,
        offset=offset,
        limit=limit,
    )
    return {
        "items": [SubscriptionOut.model_validate(s).model_dump(mode="json") for s in items],
        "total": total,
    }


@router.post(
    "/{subscription_id}/renew",
    response_model=SubscriptionOut,
    summary="Renew subscription",
)
async def renew_subscription(
    subscription_id: uuid.UUID,
    body: SubscriptionRenew,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SubscriptionOut:
    svc = SubscriptionService(db)
    try:
        sub = await svc.renew(subscription_id, body.expires_at)
    except SubscriptionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    await db.commit()
    return SubscriptionOut.model_validate(sub)


@router.post(
    "/{subscription_id}/cancel",
    response_model=SubscriptionOut,
    summary="Cancel subscription",
)
async def cancel_subscription(
    subscription_id: uuid.UUID,
    body: SubscriptionCancel,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SubscriptionOut:
    svc = SubscriptionService(db)
    try:
        sub = await svc.cancel(subscription_id, body.reason)
    except SubscriptionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    await db.commit()
    return SubscriptionOut.model_validate(sub)


@router.post("/expire-due", response_model=dict, summary="Expire due subscriptions")
async def expire_due_subscriptions(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_superuser)],
) -> dict:
    """Expire all subscriptions past their expiry date. Superuser only."""
    svc = SubscriptionService(db)
    count = await svc.expire_due()
    await db.commit()
    return {"expired_count": count}
