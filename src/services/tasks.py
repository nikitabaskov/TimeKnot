"""Task use cases. Owns the unit of work; knows repositories, not SQLAlchemy queries."""

from __future__ import annotations

import enum
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clock import Clock
from reminders import NullReminderPlanner, ReminderPlanner
from repositories.models import Task, TaskStatus
from repositories.tasks import TaskRepository
from repositories.users import UserRepository

# Fixed by decision: v1 offers no choice of interval.
SNOOZE_STEP = timedelta(hours=1)


class Outcome(enum.StrEnum):
    UPDATED = "updated"
    ALREADY_CLOSED = "already_closed"
    NOT_FOUND = "not_found"


class TaskService:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        clock: Clock,
        default_timezone: str,
        planner: ReminderPlanner | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._default_timezone = default_timezone
        self._planner = planner or NullReminderPlanner()

    async def create_task(
        self,
        user_id: int,
        *,
        title: str,
        category: str | None = None,
        due_at: datetime | None = None,
    ) -> Task:
        """Store a new pending task. `due_at` must be aware; None means no deadline."""
        async with self._session_factory() as session:
            now = self._clock.now()
            await UserRepository(session).ensure(user_id, self._default_timezone, now)
            task = await TaskRepository(session).add(
                Task(
                    user_id=user_id,
                    title=title,
                    category=category,
                    due_at=due_at,
                    created_at=now,
                )
            )
            await session.commit()

        # Armed after the commit: a timer for a task that failed to store would
        # fire against nothing. A task without a deadline never reaches the scheduler.
        if task.due_at is not None:
            self._planner.schedule(task.id, task.due_at)
        return task

    async def list_active(self, user_id: int) -> list[Task]:
        """Pending tasks of the user. Creates the user row on first contact."""
        async with self._session_factory() as session:
            users = UserRepository(session)
            await users.ensure(user_id, self._default_timezone, self._clock.now())
            tasks = await TaskRepository(session).list_pending(user_id)
            await session.commit()
            return tasks

    async def complete(
        self,
        task_id: int,
        user_id: int,
        status: TaskStatus = TaskStatus.DONE,
    ) -> tuple[Outcome, Task | None]:
        """Close a task as done or cancelled. Closing twice is a no-op, not an error."""
        async with self._session_factory() as session:
            task = await self._own_pending_task(session, task_id, user_id)
            if not isinstance(task, Task):
                return task, None
            task.status = status
            await session.commit()
            return Outcome.UPDATED, task

    async def snooze(self, task_id: int, user_id: int) -> tuple[Outcome, Task | None]:
        """Push a reminder one hour out and re-arm its timer."""
        async with self._session_factory() as session:
            task = await self._own_pending_task(session, task_id, user_id)
            if not isinstance(task, Task):
                return task, None

            # Measured from the later of the two: after downtime a caught-up
            # reminder can be hours overdue, and "again in an hour" must mean an
            # hour from now, not an hour from a moment already past.
            base = max(task.due_at or self._clock.now(), self._clock.now())
            task.due_at = base + SNOOZE_STEP
            # Cleared, or dispatch_due would consider this reminder already delivered.
            task.reminder_sent_at = None
            await session.commit()
            due_at = task.due_at

        self._planner.schedule(task_id, due_at)
        return Outcome.UPDATED, task

    async def _own_pending_task(
        self, session: AsyncSession, task_id: int, user_id: int
    ) -> Task | Outcome:
        task = await TaskRepository(session).get(task_id)
        if task is None or task.user_id != user_id:
            return Outcome.NOT_FOUND
        if task.status is not TaskStatus.PENDING:
            return Outcome.ALREADY_CLOSED
        return task
