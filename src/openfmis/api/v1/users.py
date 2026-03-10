"""User CRUD endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.schemas.user import (
    PasswordChange,
    UserCreate,
    UserList,
    UserRead,
    UserUpdate,
)
from openfmis.services.user import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UserList)
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    group_id: UUID | None = None,
    is_active: bool | None = None,
) -> UserList:
    svc = UserService(db)
    users, total = await svc.list_users(
        offset=offset, limit=limit, group_id=group_id, is_active=is_active
    )
    return UserList(items=[UserRead.model_validate(u) for u in users], total=total)


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    svc = UserService(db)
    return await svc.get_by_id(user_id)


@router.post("", response_model=UserRead, status_code=201)
async def create_user(
    body: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    svc = UserService(db)
    return await svc.create_user(body)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: UUID,
    body: UserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    svc = UserService(db)
    return await svc.update_user(user_id, body)


@router.post("/{user_id}/change-password", status_code=204)
async def change_password(
    user_id: UUID,
    body: PasswordChange,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    svc = UserService(db)
    await svc.change_password(user_id, body.current_password, body.new_password)


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    svc = UserService(db)
    await svc.soft_delete(user_id)
