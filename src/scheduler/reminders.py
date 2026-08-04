"""APScheduler wiring.

The scheduler is a cache of timers, nothing more. `MemoryJobStore` is deliberate:
a persistent jobstore would be a second copy of state that drifts from the
`tasks` table as tasks are edited, closed and snoozed.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from clock import Clock
from services.reminders import ReminderService

logger = logging.getLogger(__name__)


def job_id(task_id: int) -> str:
    return f"task:{task_id}"


class ReminderScheduler:
    def __init__(self, reminder_service: ReminderService, clock: Clock) -> None:
        self._reminder_service = reminder_service
        self._clock = clock
        # UTC explicitly: everything handed to the scheduler is UTC, and the
        # default would be whatever tzlocal reports on the host.
        self._scheduler = AsyncIOScheduler(jobstores={"default": MemoryJobStore()}, timezone=UTC)

    def start(self) -> None:
        self._scheduler.start()

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)

    def schedule(self, task_id: int, due_at: datetime) -> None:
        if not self._scheduler.running:
            # While stopped, APScheduler only queues jobs and never applies
            # replace_existing, so a rescheduled task would silently gain a
            # second timer. Fail loudly instead.
            raise RuntimeError("ReminderScheduler.start() must be called before scheduling")
        self._scheduler.add_job(
            self._fire,
            "date",
            run_date=due_at,
            args=[due_at],
            id=job_id(task_id),
            replace_existing=True,
        )

    async def _fire(self, scheduled_for: datetime) -> None:
        # The timer may fire a hair early; taking the later of the two moments
        # keeps the task inside the `due_at <= now` window it was armed for.
        now = max(self._clock.now(), scheduled_for)
        sent = await self._reminder_service.dispatch_due(now)
        logger.info("Dispatched %d reminder(s)", len(sent))
