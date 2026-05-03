"""Authentication endpoints — login, logout, refresh, me."""

import uuid as _uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.exceptions import AuthenticationError
from openfmis.models.user import User
from openfmis.schemas.auth import LoginRequest, RefreshRequest, TokenResponse
from openfmis.schemas.user import UserRead
from openfmis.security.jwt import decode_access_token
from openfmis.services.auth import AuthService
from openfmis.services.session_audit import SessionAuditService

router = APIRouter(tags=["auth"])
bearer_scheme = HTTPBearer()


@router.post("/login", response_model=TokenResponse, summary="Login")
async def login(
    body: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    audit = SessionAuditService(db)
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    svc = AuthService(db)
    try:
        access, refresh = await svc.authenticate(body.username, body.password)
    except AuthenticationError:
        # Record failed login attempt — need to find user_id if possible
        from openfmis.services.user import UserService

        user_svc = UserService(db)
        user = await user_svc.get_by_username(body.username)
        if user is not None:
            await audit.record(user.id, "login_failed", ip_address=ip, user_agent=ua)
        raise
    # Decode to get jti and user_id
    payload = decode_access_token(access)
    jti = payload.get("jti") if payload else None
    sub = payload.get("sub") if payload else None
    if sub:
        await audit.record(_uuid.UUID(sub), "login", ip_address=ip, user_agent=ua, jti=jti)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse, summary="Refresh")
async def refresh(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    svc = AuthService(db)
    access, refresh = await svc.refresh_tokens(body.refresh_token)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/logout", status_code=204, summary="Logout")
async def logout(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    user: Annotated[User, Depends(get_current_user)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Revoke the current access token by adding its JTI to the blacklist."""
    payload = decode_access_token(credentials.credentials)
    if payload and "jti" in payload and "exp" in payload:
        svc = AuthService(db)
        expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
        await svc.logout(payload["jti"], expires_at)
        # Record logout
        audit = SessionAuditService(db)
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")
        await audit.record(user.id, "logout", ip_address=ip, user_agent=ua, jti=payload["jti"])


@router.get("/me", response_model=UserRead, summary="Me")
async def me(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    return user


@router.get("/auth/sessions", summary="List sessions")
async def list_sessions(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    event_type: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> dict:
    """Return the current user's session audit log."""
    audit = SessionAuditService(db)
    entries, total = await audit.list_for_user(
        user.id, event_type=event_type, offset=offset, limit=limit
    )
    return {
        "items": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "ip_address": e.ip_address,
                "user_agent": e.user_agent,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ],
        "total": total,
    }
