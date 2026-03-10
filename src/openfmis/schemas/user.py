"""User CRUD schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserRead(BaseModel):
    id: UUID
    username: str
    email: str | None = None
    full_name: str | None = None
    is_active: bool
    is_superuser: bool
    group_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=255)
    email: EmailStr | None = None
    password: str = Field(..., min_length=8)
    full_name: str | None = None
    group_id: UUID | None = None
    is_superuser: bool = False


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = None
    is_active: bool | None = None
    group_id: UUID | None = None


class PasswordChange(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)


class UserList(BaseModel):
    items: list[UserRead]
    total: int
