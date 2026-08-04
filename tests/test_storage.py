"""Storage invariants: UTC everywhere, constrained statuses, real foreign keys."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.models import Task, TaskStatus
from repositories.tasks import TaskRepository
from repositories.users import UserRepository
from tests.conftest import NOW, OWNER_ID, TIMEZONE

KRASNOYARSK = ZoneInfo(TIMEZONE)


async def add_owner(session: AsyncSession) -> None:
    await UserRepository(session).ensure(OWNER_ID, TIMEZONE, NOW)


async def test_user_row_is_created_once(session: AsyncSession) -> None:
    users = UserRepository(session)

    first = await users.ensure(OWNER_ID, TIMEZONE, NOW)
    second = await users.ensure(OWNER_ID, "Europe/Moscow", NOW)

    assert first.id == second.id == OWNER_ID
    assert second.timezone == TIMEZONE, "an existing row must not be overwritten"
    assert len(await users.list_all()) == 1


async def test_local_time_round_trips_as_utc(session: AsyncSession) -> None:
    await add_owner(session)
    local_due = datetime(2026, 8, 5, 19, 0, tzinfo=KRASNOYARSK)
    tasks = TaskRepository(session)

    stored = await tasks.add(
        Task(user_id=OWNER_ID, title="Купить корм коту", due_at=local_due, created_at=NOW)
    )
    session.expunge_all()
    reloaded = await tasks.get(stored.id)

    assert reloaded is not None
    assert reloaded.due_at == datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
    assert reloaded.due_at.tzinfo is not None, "reads must come back aware"
    assert reloaded.due_at.astimezone(KRASNOYARSK).hour == 19


async def test_naive_datetime_is_rejected(session: AsyncSession) -> None:
    await add_owner(session)
    naive = datetime(2026, 8, 5, 19, 0)

    with pytest.raises(StatementError):
        await TaskRepository(session).add(
            Task(user_id=OWNER_ID, title="без пояса", due_at=naive, created_at=NOW)
        )


async def test_new_task_defaults(session: AsyncSession) -> None:
    await add_owner(session)

    task = await TaskRepository(session).add(
        Task(user_id=OWNER_ID, title="Почитать книгу", created_at=NOW)
    )

    assert task.status == TaskStatus.PENDING
    assert task.due_at is None
    assert task.rrule is None
    assert task.reminder_sent_at is None


async def test_unknown_status_is_rejected(session: AsyncSession) -> None:
    await add_owner(session)

    with pytest.raises(StatementError):
        await TaskRepository(session).add(
            Task(user_id=OWNER_ID, title="x", created_at=NOW, status="postponed")
        )


async def test_unknown_status_is_rejected_by_the_database_too(session: AsyncSession) -> None:
    """Bypasses the ORM to prove the CHECK constraint exists, not just Python validation."""
    await add_owner(session)

    with pytest.raises(IntegrityError):
        await session.execute(
            text(
                "INSERT INTO tasks (user_id, title, status, created_at) "
                "VALUES (:user_id, 'x', 'postponed', :created_at)"
            ),
            {"user_id": OWNER_ID, "created_at": NOW.replace(tzinfo=None).isoformat(sep=" ")},
        )


async def test_task_without_user_is_rejected(session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await TaskRepository(session).add(Task(user_id=999, title="ничей", created_at=NOW))


async def test_list_pending_skips_closed_and_orders_undated_last(session: AsyncSession) -> None:
    await add_owner(session)
    tasks = TaskRepository(session)
    later = datetime(2026, 8, 6, 10, 0, tzinfo=UTC)
    sooner = datetime(2026, 8, 5, 10, 0, tzinfo=UTC)
    await tasks.add(Task(user_id=OWNER_ID, title="позже", due_at=later, created_at=NOW))
    await tasks.add(Task(user_id=OWNER_ID, title="без срока", created_at=NOW))
    await tasks.add(Task(user_id=OWNER_ID, title="раньше", due_at=sooner, created_at=NOW))
    await tasks.add(Task(user_id=OWNER_ID, title="закрыта", created_at=NOW, status=TaskStatus.DONE))

    pending = await tasks.list_pending(OWNER_ID)

    assert [task.title for task in pending] == ["раньше", "позже", "без срока"]
