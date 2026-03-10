"""Authentication endpoints — login, logout, refresh, me."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.schemas.auth import LoginRequest, RefreshRequest, TokenResponse
from openfmis.schemas.user import UserRead
from openfmis.security.jwt import decode_access_token
from openfmis.services.auth import AuthService

router = APIRouter(tags=["auth"])
bearer_scheme = HTTPBearer()


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    svc = AuthService(db)
    access, refresh = await svc.authenticate(body.username, body.password)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    svc = AuthService(db)
    access, refresh = await svc.refresh_tokens(body.refresh_token)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/logout", status_code=204)
async def logout(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Revoke the current access token by adding its JTI to the blacklist."""
    payload = decode_access_token(credentials.credentials)
    if payload and "jti" in payload and "exp" in payload:
        svc = AuthService(db)
        expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
        await svc.logout(payload["jti"], expires_at)


@router.get("/me", response_model=UserRead)
async def me(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    return user
