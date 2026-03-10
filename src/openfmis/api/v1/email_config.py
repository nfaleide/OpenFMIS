"""Email configuration endpoints — SMTP or webhook setup per group."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.services.email_delivery import EmailDeliveryService

router = APIRouter(prefix="/satshot/email-config", tags=["satshot-email"])


class EmailConfigUpdate(BaseModel):
    delivery_method: str = "smtp"
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    smtp_from_address: str | None = None
    webhook_url: str | None = None
    webhook_headers: dict | None = None
    webhook_secret: str | None = None


class TestEmailRequest(BaseModel):
    to: str


@router.get("/", response_model=dict | None)
async def get_config(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    group_id = getattr(current_user, "group_id", None)
    if not group_id:
        return None
    svc = EmailDeliveryService(db)
    config = await svc.get_config(group_id)
    if config is None:
        return None
    return {
        "delivery_method": config.delivery_method,
        "smtp_host": config.smtp_host,
        "smtp_port": config.smtp_port,
        "smtp_username": config.smtp_username,
        "smtp_use_tls": config.smtp_use_tls,
        "smtp_from_address": config.smtp_from_address,
        "webhook_url": config.webhook_url,
        "is_active": config.is_active,
    }


@router.put("/", response_model=dict)
async def update_config(
    data: EmailConfigUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    group_id = getattr(current_user, "group_id", None)
    if not group_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a group"
        )
    svc = EmailDeliveryService(db)
    config = await svc.set_config(group_id, **data.model_dump())
    await db.commit()
    return {"status": "saved", "delivery_method": config.delivery_method}


@router.post("/test", response_model=dict)
async def test_email(
    data: TestEmailRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    group_id = getattr(current_user, "group_id", None)
    if not group_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a group"
        )
    svc = EmailDeliveryService(db)
    return await svc.send_test(group_id, data.to)
