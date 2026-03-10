"""UserService — CRUD operations + password management."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import ConflictError, NotFoundError
from openfmis.models.user import User
from openfmis.schemas.user import UserCreate, UserUpdate
from openfmis.security.password import hash_password, verify_password


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: UUID) -> User:
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise NotFoundError("User not found")
        return user

    async def get_by_username(self, username: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.username == username, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_users(
        self,
        offset: int = 0,
        limit: int = 50,
        group_id: UUID | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[User], int]:
        query = select(User).where(User.deleted_at.is_(None))
        count_query = select(func.count()).select_from(User).where(User.deleted_at.is_(None))

        if group_id is not None:
            query = query.where(User.group_id == group_id)
            count_query = count_query.where(User.group_id == group_id)
        if is_active is not None:
            query = query.where(User.is_active == is_active)
            count_query = count_query.where(User.is_active == is_active)

        query = query.order_by(User.username).offset(offset).limit(limit)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        result = await self.db.execute(query)
        users = list(result.scalars().all())
        return users, total

    async def create_user(self, data: UserCreate) -> User:
        # Check uniqueness
        existing = await self.get_by_username(data.username)
        if existing is not None:
            raise ConflictError(f"Username '{data.username}' already exists")

        if data.email:
            email_check = await self.db.execute(
                select(User).where(User.email == data.email, User.deleted_at.is_(None))
            )
            if email_check.scalar_one_or_none() is not None:
                raise ConflictError(f"Email '{data.email}' already in use")

        user = User(
            username=data.username,
            email=data.email,
            password_hash=hash_password(data.password),
            full_name=data.full_name,
            group_id=data.group_id,
            is_superuser=data.is_superuser,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def update_user(self, user_id: UUID, data: UserUpdate) -> User:
        user = await self.get_by_id(user_id)

        if data.email is not None and data.email != user.email:
            email_check = await self.db.execute(
                select(User).where(
                    User.email == data.email,
                    User.id != user_id,
                    User.deleted_at.is_(None),
                )
            )
            if email_check.scalar_one_or_none() is not None:
                raise ConflictError(f"Email '{data.email}' already in use")

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(user, field, value)

        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def change_password(
        self, user_id: UUID, current_password: str, new_password: str
    ) -> None:
        user = await self.get_by_id(user_id)
        if not verify_password(current_password, user.password_hash):
            from openfmis.exceptions import AuthenticationError

            raise AuthenticationError("Current password is incorrect")
        user.password_hash = hash_password(new_password)
        await self.db.flush()

    async def soft_delete(self, user_id: UUID) -> None:
        from datetime import UTC, datetime

        user = await self.get_by_id(user_id)
        user.deleted_at = datetime.now(UTC)
        user.is_active = False
        await self.db.flush()
