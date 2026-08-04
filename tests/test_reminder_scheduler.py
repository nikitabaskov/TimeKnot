"""The APScheduler wrapper. Job registration only — firing is covered through dispatch_due."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from scheduler.reminders import ReminderScheduler, job_id
from services.reminders import ReminderService
from tests.conftest import NOW, FixedClock, SenderSpy

DUE = NOW + timedelta(minutes=2)


@pytest.fixture
async def scheduler(session_factory: async_sessionmaker) -> AsyncIterator[ReminderScheduler]:
    scheduler = ReminderScheduler(ReminderService(session_factory, SenderSpy()), FixedClock())
    scheduler.start()
    yield scheduler
    scheduler.shutdown()


async def test_scheduling_registers_one_job_per_task(scheduler: ReminderScheduler) -> None:
    scheduler.schedule(task_id=7, due_at=DUE)

    job = scheduler._scheduler.get_job(job_id(7))
    assert job is not None
    assert job.trigger.run_date == DUE


async def test_rescheduling_a_task_replaces_its_job(scheduler: ReminderScheduler) -> None:
    """Snoozing must move the timer, not add a second one."""
    later = DUE + timedelta(hours=1)

    scheduler.schedule(task_id=7, due_at=DUE)
    scheduler.schedule(task_id=7, due_at=later)

    assert len(scheduler._scheduler.get_jobs()) == 1
    assert scheduler._scheduler.get_job(job_id(7)).trigger.run_date == later


async def test_scheduling_before_start_is_refused(session_factory: async_sessionmaker) -> None:
    """A stopped APScheduler silently ignores replace_existing, so this must not pass."""
    stopped = ReminderScheduler(ReminderService(session_factory, SenderSpy()), FixedClock())

    with pytest.raises(RuntimeError, match="start"):
        stopped.schedule(task_id=7, due_at=DUE)


async def test_firing_dispatches_at_the_moment_the_job_was_armed_for(
    session_factory: async_sessionmaker,
) -> None:
    """A timer that fires a hair early must not miss its own `due_at <= now` window."""
    seen: list[object] = []

    class RecordingService:
        async def dispatch_due(self, now: object) -> list[object]:
            seen.append(now)
            return []

    scheduler = ReminderScheduler(RecordingService(), FixedClock(NOW))  # type: ignore[arg-type]

    await scheduler._fire(DUE)

    assert seen == [DUE], "the clock reads before due_at, so the armed moment wins"
