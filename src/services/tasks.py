"""Task use cases. Owns the unit of work; knows repositories, not SQLAlchemy queries."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker

from clock import Clock
from repositories.models import Task
from repositories.tasks import TaskRepository
from repositories.users import UserRepository


class TaskService:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        clock: Clock,
        default_timezone: str,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._default_timezone = default_timezone

    async def list_active(self, user_id: int) -> list[Task]:
        """Pending tasks of the user. Creates the user row on first contact."""
        async with self._session_factory() as session:
            users = UserRepository(session)
            await users.ensure(user_id, self._default_timezone, self._clock.now())
            tasks = await TaskRepository(session).list_pending(user_id)
            await session.commit()
            return tasks
