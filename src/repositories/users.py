"""User repository."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def ensure(self, user_id: int, timezone: str, now: datetime) -> User:
        """Return the stored user, creating the row on first contact."""
        user = await self.get(user_id)
        if user is not None:
            return user
        user = User(id=user_id, timezone=timezone, created_at=now)
        self._session.add(user)
        await self._session.flush()
        return user

    async def list_all(self) -> list[User]:
        result = await self._session.scalars(select(User).order_by(User.id))
        return list(result)
