"""Surviving a restart: the tasks table alone rebuilds the timers.

Each test writes tasks, then brings a scheduler up on a clock moved forward,
exactly as a process restarted after downtime would see the world.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repositories.models import Task, TaskStatus
from repositories.tasks import TaskRepository
from repositories.users import UserRepository
from scheduler.reminders import ReminderScheduler, job_id
from services.reminders import ReminderService
from tests.conftest import NOW, OWNER_ID, TIMEZONE, FixedClock, SenderSpy

OVERDUE = NOW - timedelta(hours=3)
UPCOMING = NOW + timedelta(hours=3)


async def store(
    session_factory: async_sessionmaker,
    *,
    title: str,
    due_at: object = None,
    status: TaskStatus = TaskStatus.PENDING,
    reminder_sent_at: object = None,
) -> int:
    async with session_factory() as session:
        await UserRepository(session).ensure(OWNER_ID, TIMEZONE, NOW)
        task = await TaskRepository(session).add(
            Task(
                user_id=OWNER_ID,
                title=title,
                due_at=due_at,
                status=status,
                created_at=OVERDUE,
                reminder_sent_at=reminder_sent_at,
            )
        )
        await session.commit()
        return task.id


@pytest.fixture
async def restarted(
    session_factory: async_sessionmaker, sender: SenderSpy
) -> AsyncIterator[ReminderScheduler]:
    """A scheduler brought up at NOW, as after a restart."""
    scheduler = ReminderScheduler(ReminderService(session_factory, sender), FixedClock(NOW))
    scheduler.start()
    yield scheduler
    scheduler.shutdown()


async def test_overdue_reminders_go_out_at_once_marked_late(
    restarted: ReminderScheduler, sender: SenderSpy, session_factory: async_sessionmaker
) -> None:
    await store(session_factory, title="Купить корм коту", due_at=OVERDUE)

    await restarted.rehydrate()

    assert sender.sent == [(OWNER_ID, "Напоминание (с опозданием): «Купить корм коту»")]


async def test_future_reminders_are_armed_not_sent(
    restarted: ReminderScheduler, sender: SenderSpy, session_factory: async_sessionmaker
) -> None:
    task_id = await store(session_factory, title="Проверить PR", due_at=UPCOMING)

    await restarted.rehydrate()

    assert sender.sent == []
    job = restarted._scheduler.get_job(job_id(task_id))
    assert job is not None
    assert job.trigger.run_date == UPCOMING


@pytest.mark.parametrize("status", [TaskStatus.DONE, TaskStatus.CANCELLED])
async def test_closed_tasks_are_ignored(
    restarted: ReminderScheduler,
    sender: SenderSpy,
    session_factory: async_sessionmaker,
    status: TaskStatus,
) -> None:
    await store(session_factory, title="просроченная закрытая", due_at=OVERDUE, status=status)
    await store(session_factory, title="будущая закрытая", due_at=UPCOMING, status=status)

    await restarted.rehydrate()

    assert sender.sent == []
    assert restarted._scheduler.get_jobs() == []


async def test_undated_tasks_never_reach_the_scheduler(
    restarted: ReminderScheduler, sender: SenderSpy, session_factory: async_sessionmaker
) -> None:
    await store(session_factory, title="Почитать книгу", due_at=None)

    await restarted.rehydrate()

    assert sender.sent == []
    assert restarted._scheduler.get_jobs() == []


async def test_restarting_again_does_not_resend(
    restarted: ReminderScheduler, sender: SenderSpy, session_factory: async_sessionmaker
) -> None:
    """`reminder_sent_at` is what keeps a second boot quiet."""
    await store(session_factory, title="Купить корм коту", due_at=OVERDUE)

    await restarted.rehydrate()
    await restarted.rehydrate()

    assert len(sender.sent) == 1


async def test_a_mixed_backlog_is_split_correctly(
    restarted: ReminderScheduler,
    sender: SenderSpy,
    session_factory: async_sessionmaker,
    session: AsyncSession,
) -> None:
    await store(session_factory, title="просрочена", due_at=OVERDUE)
    upcoming_id = await store(session_factory, title="впереди", due_at=UPCOMING)
    await store(session_factory, title="уже отправлена", due_at=OVERDUE, reminder_sent_at=OVERDUE)
    await store(session_factory, title="закрыта", due_at=OVERDUE, status=TaskStatus.DONE)
    await store(session_factory, title="без срока", due_at=None)

    await restarted.rehydrate()

    assert [text for _user_id, text in sender.sent] == ["Напоминание (с опозданием): «просрочена»"]
    assert [job.id for job in restarted._scheduler.get_jobs()] == [job_id(upcoming_id)]


async def test_an_on_time_reminder_is_not_announced_as_late(
    session_factory: async_sessionmaker, sender: SenderSpy
) -> None:
    """Only a catch-up carries the marker; a timer firing on schedule does not."""
    just_due = NOW - timedelta(seconds=5)
    await store(session_factory, title="Купить корм коту", due_at=just_due)

    await ReminderService(session_factory, sender).dispatch_due(NOW)

    assert sender.sent == [(OWNER_ID, "Напоминание: «Купить корм коту»")]
