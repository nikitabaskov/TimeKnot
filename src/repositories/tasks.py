"""Task repository."""

from __future__ import annotations

from datetime import datetime

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

    async def list_due(self, now: datetime) -> list[Task]:
        """Pending tasks whose moment has arrived and whose reminder has not gone out.

        This query is the re-read of the status: a task closed after its job was
        armed simply is not selected.
        """
        statement = (
            select(Task)
            .where(
                Task.status == TaskStatus.PENDING,
                Task.due_at.is_not(None),
                Task.due_at <= now,
                Task.reminder_sent_at.is_(None),
            )
            .order_by(Task.due_at, Task.id)
        )
        result = await self._session.scalars(statement)
        return list(result)

    async def list_upcoming(self, now: datetime) -> list[Task]:
        """Open tasks whose moment is still ahead — the ones a timer must be armed for."""
        statement = (
            select(Task)
            .where(
                Task.status == TaskStatus.PENDING,
                Task.due_at.is_not(None),
                Task.due_at > now,
            )
            .order_by(Task.due_at, Task.id)
        )
        result = await self._session.scalars(statement)
        return list(result)

    async def mark_reminder_sent(self, task: Task, at: datetime) -> None:
        task.reminder_sent_at = at
        await self._session.flush()

    async def list_pending(self, user_id: int) -> list[Task]:
        """Pending tasks, dated ones first by due date, undated ones last."""
        statement = (
            select(Task)
            .where(Task.user_id == user_id, Task.status == TaskStatus.PENDING)
            .order_by(Task.due_at.is_(None), Task.due_at, Task.id)
        )
        result = await self._session.scalars(statement)
        return list(result)
