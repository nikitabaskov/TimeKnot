"""`dispatch_due` — the scheduler seam. Current moment in, sent reminders out."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker

from reminders import ReminderSender
from rendering import render_reminder
from repositories.models import Task
from repositories.tasks import TaskRepository

logger = logging.getLogger(__name__)

# A reminder that goes out this far past its moment is announced as late. Normal
# firing is a fraction of a second off; only a catch-up after downtime is not.
LATE_AFTER = timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class SentReminder:
    task_id: int
    user_id: int
    text: str


class ReminderService:
    def __init__(self, session_factory: async_sessionmaker, sender: ReminderSender) -> None:
        self._session_factory = session_factory
        self._sender = sender

    async def dispatch_due(self, now: datetime) -> list[SentReminder]:
        """Send every reminder that has come due and is still open.

        Delivery is at-least-once: a task is marked only after its send
        succeeded, so a crash in between repeats a reminder rather than losing it.
        """
        sent: list[SentReminder] = []
        async with self._session_factory() as session:
            tasks = TaskRepository(session)
            for task in await tasks.list_due(now):
                text = render_reminder(task, late=now - task.due_at > LATE_AFTER)
                try:
                    await self._sender.send(user_id=task.user_id, text=text, task_id=task.id)
                except Exception:
                    # One unreachable chat must not hold up the rest. The task stays
                    # unmarked and goes out on the next dispatch or after a restart.
                    logger.exception("Failed to send reminder for task %s", task.id)
                    continue
                await tasks.mark_reminder_sent(task, now)
                await session.commit()
                sent.append(SentReminder(task_id=task.id, user_id=task.user_id, text=text))
        return sent

    async def list_upcoming(self, now: datetime) -> list[Task]:
        """Open tasks still ahead of `now`, so their timers can be armed on startup."""
        async with self._session_factory() as session:
            return await TaskRepository(session).list_upcoming(now)
