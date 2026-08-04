"""Task repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.models import Task, TaskStatus


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, task: Task) -> Task:
        self._session.add(task)
        await self._session.flush()
        return task

    async def get(self, task_id: int) -> Task | None:
        return await self._session.get(Task, task_id)

    async def list_pending(self, user_id: int) -> list[Task]:
        """Pending tasks, dated ones first by due date, undated ones last."""
        statement = (
            select(Task)
            .where(Task.user_id == user_id, Task.status == TaskStatus.PENDING)
            .order_by(Task.due_at.is_(None), Task.due_at, Task.id)
        )
        result = await self._session.scalars(statement)
        return list(result)
