"""The scheduler seam: a fixed moment in, sent reminders out.

No test here waits on wall-clock time; `dispatch_due` is called with the moment
under test.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repositories.models import Task, TaskStatus
from repositories.tasks import TaskRepository
from repositories.users import UserRepository
from services.reminders import ReminderService
from tests.conftest import NOW, OWNER_ID, TIMEZONE, PlannerSpy, SenderSpy

DUE = NOW + timedelta(minutes=2)
AFTER_DUE = DUE + timedelta(seconds=1)


async def store_task(
    session_factory: async_sessionmaker,
    *,
    title: str = "Купить корм коту",
    due_at: datetime | None = DUE,
    status: TaskStatus = TaskStatus.PENDING,
    reminder_sent_at: datetime | None = None,
) -> int:
    async with session_factory() as session:
        await UserRepository(session).ensure(OWNER_ID, TIMEZONE, NOW)
        task = await TaskRepository(session).add(
            Task(
                user_id=OWNER_ID,
                title=title,
                due_at=due_at,
                status=status,
                created_at=NOW,
                reminder_sent_at=reminder_sent_at,
            )
        )
        await session.commit()
        return task.id


async def test_due_task_is_sent_and_marked(
    reminder_service: ReminderService,
    sender: SenderSpy,
    session_factory: async_sessionmaker,
    session: AsyncSession,
) -> None:
    task_id = await store_task(session_factory)

    sent = await reminder_service.dispatch_due(AFTER_DUE)

    assert [reminder.task_id for reminder in sent] == [task_id]
    assert sender.sent == [(OWNER_ID, "Напоминание: «Купить корм коту»")]
    stored = await TaskRepository(session).get(task_id)
    assert stored is not None
    assert stored.reminder_sent_at == AFTER_DUE
    assert stored.status == TaskStatus.PENDING, "sending a reminder does not close the task"


async def test_task_is_not_sent_before_its_moment(
    reminder_service: ReminderService, sender: SenderSpy, session_factory: async_sessionmaker
) -> None:
    await store_task(session_factory)

    sent = await reminder_service.dispatch_due(NOW)

    assert sent == []
    assert sender.sent == []


async def test_closed_task_produces_no_reminder(
    reminder_service: ReminderService, sender: SenderSpy, session_factory: async_sessionmaker
) -> None:
    """The status is re-read at dispatch time, so a task closed meanwhile stays quiet."""
    await store_task(session_factory, status=TaskStatus.DONE)
    await store_task(session_factory, title="отменённая", status=TaskStatus.CANCELLED)

    sent = await reminder_service.dispatch_due(AFTER_DUE)

    assert sent == []
    assert sender.sent == []


async def test_task_without_a_deadline_is_never_due(
    reminder_service: ReminderService, sender: SenderSpy, session_factory: async_sessionmaker
) -> None:
    await store_task(session_factory, title="Почитать книгу", due_at=None)

    sent = await reminder_service.dispatch_due(AFTER_DUE + timedelta(days=365))

    assert sent == []
    assert sender.sent == []


async def test_a_reminder_is_not_repeated_on_the_next_dispatch(
    reminder_service: ReminderService, sender: SenderSpy, session_factory: async_sessionmaker
) -> None:
    await store_task(session_factory)

    first = await reminder_service.dispatch_due(AFTER_DUE)
    second = await reminder_service.dispatch_due(AFTER_DUE + timedelta(hours=1))

    assert len(first) == 1
    assert second == []
    assert len(sender.sent) == 1


async def test_overdue_tasks_go_out_oldest_first(
    reminder_service: ReminderService, sender: SenderSpy, session_factory: async_sessionmaker
) -> None:
    await store_task(session_factory, title="позже", due_at=DUE + timedelta(minutes=5))
    await store_task(session_factory, title="раньше", due_at=DUE)

    sent = await reminder_service.dispatch_due(AFTER_DUE + timedelta(hours=1))

    assert [reminder.text for reminder in sent] == [
        "Напоминание (с опозданием): «раньше»",
        "Напоминание (с опозданием): «позже»",
    ]


async def test_a_failed_send_leaves_the_task_unmarked(
    session_factory: async_sessionmaker, session: AsyncSession
) -> None:
    """At-least-once: a task is marked sent only after the send succeeded."""

    class BrokenSender:
        async def send(self, *, user_id: int, text: str) -> None:
            raise RuntimeError("Telegram is down")

    task_id = await store_task(session_factory)
    service = ReminderService(session_factory, BrokenSender())

    sent = await service.dispatch_due(AFTER_DUE)

    assert sent == []
    stored = await TaskRepository(session).get(task_id)
    assert stored is not None
    assert stored.reminder_sent_at is None


async def test_one_broken_send_does_not_block_the_others(
    session_factory: async_sessionmaker,
) -> None:
    class FlakySender:
        def __init__(self) -> None:
            self.sent: list[str] = []

        async def send(self, *, user_id: int, text: str) -> None:
            if "раньше" in text:
                raise RuntimeError("Telegram is down")
            self.sent.append(text)

    await store_task(session_factory, title="раньше", due_at=DUE)
    await store_task(session_factory, title="позже", due_at=DUE + timedelta(minutes=5))
    sender = FlakySender()

    sent = await ReminderService(session_factory, sender).dispatch_due(
        AFTER_DUE + timedelta(hours=1)
    )

    assert [reminder.text for reminder in sent] == ["Напоминание (с опозданием): «позже»"]
    assert sender.sent == ["Напоминание (с опозданием): «позже»"]


async def test_creating_a_dated_task_arms_a_timer(
    session_factory: async_sessionmaker, planner: PlannerSpy
) -> None:
    from clock import Clock
    from services.tasks import TaskService

    class Fixed(Clock):
        def now(self) -> datetime:
            return NOW

    service = TaskService(session_factory, Fixed(), TIMEZONE, planner=planner)

    dated = await service.create_task(OWNER_ID, title="со сроком", due_at=DUE)
    await service.create_task(OWNER_ID, title="без срока", due_at=None)

    assert planner.scheduled == [(dated.id, DUE)], "an undated task never reaches the scheduler"


async def test_reminder_moment_is_compared_in_utc(
    reminder_service: ReminderService, sender: SenderSpy, session_factory: async_sessionmaker
) -> None:
    """`due_at` is stored in UTC, so a local-time `now` must still line up."""
    from tests.conftest import KRASNOYARSK

    await store_task(session_factory, due_at=datetime(2026, 8, 5, 12, 0, tzinfo=UTC))

    local_now = datetime(2026, 8, 5, 19, 1, tzinfo=KRASNOYARSK)
    sent = await reminder_service.dispatch_due(local_now)

    assert len(sent) == 1
