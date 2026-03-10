"""EmailDeliveryService — pluggable email delivery (SMTP or webhook).

Users can connect their own email system via webhook,
or use built-in SMTP delivery.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from openfmis.models.base import Base

log = logging.getLogger(__name__)


# ── Email config model ───────────────────────────────────────────────────────


class EmailConfig(Base):
    """Per-group email delivery configuration."""

    __tablename__ = "email_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    delivery_method: Mapped[str] = mapped_column(String(20), nullable=False, default="smtp")
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    smtp_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    smtp_use_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    smtp_from_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    webhook_headers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    webhook_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


# ── Attachment dataclass ─────────────────────────────────────────────────────


@dataclass
class Attachment:
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


# ── Service ──────────────────────────────────────────────────────────────────


class EmailDeliveryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_config(self, group_id: uuid.UUID) -> EmailConfig | None:
        result = await self.db.execute(select(EmailConfig).where(EmailConfig.group_id == group_id))
        return result.scalar_one_or_none()

    async def set_config(
        self,
        group_id: uuid.UUID,
        delivery_method: str = "smtp",
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        smtp_username: str | None = None,
        smtp_password: str | None = None,
        smtp_use_tls: bool = True,
        smtp_from_address: str | None = None,
        webhook_url: str | None = None,
        webhook_headers: dict | None = None,
        webhook_secret: str | None = None,
    ) -> EmailConfig:
        config = await self.get_config(group_id)
        if config is None:
            config = EmailConfig(group_id=group_id)
            self.db.add(config)

        config.delivery_method = delivery_method
        config.smtp_host = smtp_host
        config.smtp_port = smtp_port
        config.smtp_username = smtp_username
        if smtp_password is not None:
            config.smtp_password_encrypted = smtp_password  # TODO: encrypt at rest
        config.smtp_use_tls = smtp_use_tls
        config.smtp_from_address = smtp_from_address
        config.webhook_url = webhook_url
        config.webhook_headers = webhook_headers
        config.webhook_secret = webhook_secret

        await self.db.flush()
        await self.db.refresh(config)
        return config

    async def send(
        self,
        group_id: uuid.UUID,
        to: str,
        subject: str,
        html_body: str,
        attachments: list[Attachment] | None = None,
    ) -> dict:
        """Send email using the group's configured delivery method."""
        config = await self.get_config(group_id)
        if config is None or not config.is_active:
            return {"status": "skipped", "reason": "No active email config for group"}

        if config.delivery_method == "smtp":
            return await self._send_smtp(config, to, subject, html_body, attachments)
        elif config.delivery_method == "webhook":
            return await self._send_webhook(config, to, subject, html_body, attachments)
        else:
            return {
                "status": "error",
                "reason": f"Unknown delivery method: {config.delivery_method}",
            }

    async def send_test(self, group_id: uuid.UUID, to: str) -> dict:
        """Send a test email to verify configuration."""
        return await self.send(
            group_id,
            to,
            subject="OpenFMIS Email Test",
            html_body="<h1>Email delivery is working!</h1><p>This is a test from OpenFMIS.</p>",
        )

    async def _send_smtp(
        self,
        config: EmailConfig,
        to: str,
        subject: str,
        html_body: str,
        attachments: list[Attachment] | None,
    ) -> dict:
        """Send via SMTP using aiosmtplib."""
        try:
            from email import encoders
            from email.mime.base import MIMEBase
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            import aiosmtplib

            msg = MIMEMultipart()
            msg["From"] = config.smtp_from_address or config.smtp_username or ""
            msg["To"] = to
            msg["Subject"] = subject
            msg.attach(MIMEText(html_body, "html"))

            if attachments:
                for att in attachments:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(att.content)
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", f"attachment; filename={att.filename}")
                    msg.attach(part)

            await aiosmtplib.send(
                msg,
                hostname=config.smtp_host,
                port=config.smtp_port or 587,
                username=config.smtp_username,
                password=config.smtp_password_encrypted,  # TODO: decrypt
                use_tls=config.smtp_use_tls,
            )
            return {"status": "sent", "method": "smtp", "to": to}

        except ImportError:
            return {"status": "error", "reason": "aiosmtplib not installed"}
        except Exception as exc:
            log.exception("SMTP send failed: %s", exc)
            return {"status": "error", "reason": str(exc)}

    async def _send_webhook(
        self,
        config: EmailConfig,
        to: str,
        subject: str,
        html_body: str,
        attachments: list[Attachment] | None,
    ) -> dict:
        """POST email data to configured webhook URL."""
        try:
            import base64

            import httpx

            payload: dict[str, Any] = {
                "to": to,
                "subject": subject,
                "html_body": html_body,
            }
            if attachments:
                payload["attachments"] = [
                    {
                        "filename": att.filename,
                        "content_base64": base64.b64encode(att.content).decode(),
                        "content_type": att.content_type,
                    }
                    for att in attachments
                ]

            headers = dict(config.webhook_headers or {})
            headers["Content-Type"] = "application/json"
            if config.webhook_secret:
                headers["X-Webhook-Secret"] = config.webhook_secret

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(config.webhook_url, json=payload, headers=headers)
                resp.raise_for_status()

            return {
                "status": "sent",
                "method": "webhook",
                "to": to,
                "http_status": resp.status_code,
            }

        except Exception as exc:
            log.exception("Webhook send failed: %s", exc)
            return {"status": "error", "reason": str(exc)}
