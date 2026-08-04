"""Ports the reminder machinery is described by.

They live outside every layer so that `services` can depend on them without
importing `scheduler` or `bot`, which both point inwards.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class ReminderSender(Protocol):
    async def send(self, *, user_id: int, text: str, task_id: int) -> None:
        """Deliver a reminder. Raises on failure so the task is not marked sent.

        The task id travels with the message so the transport can attach its own
        controls without `services` knowing what a Telegram keyboard is.
        """
        ...


class ReminderPlanner(Protocol):
    def schedule(self, task_id: int, due_at: datetime) -> None:
        """Arm a timer for a task. The `tasks` table stays the source of truth."""
        ...


class NullReminderPlanner:
    """Used where scheduling is irrelevant, such as storage-only tests."""

    def schedule(self, task_id: int, due_at: datetime) -> None:
        return None
