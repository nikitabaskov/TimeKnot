"""End to end: /tasks goes from the Telegram command through the service into SQLite."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.handlers import handle_tasks
from bot.rendering import EMPTY_LIST_TEXT
from repositories.models import Task
from repositories.tasks import TaskRepository
from repositories.users import UserRepository
from services.tasks import TaskService
from tests.conftest import NOW, OWNER_ID, TIMEZONE, MessageSpy

KRASNOYARSK = ZoneInfo(TIMEZONE)


async def test_empty_database_answers_that_the_list_is_empty(task_service: TaskService) -> None:
    message = MessageSpy()

    await handle_tasks(message, task_service, KRASNOYARSK)  # type: ignore[arg-type]

    assert message.answers == [EMPTY_LIST_TEXT]


async def test_owner_row_appears_on_first_contact(
    task_service: TaskService, session: AsyncSession
) -> None:
    await handle_tasks(MessageSpy(), task_service, KRASNOYARSK)  # type: ignore[arg-type]

    owner = await UserRepository(session).get(OWNER_ID)
    assert owner is not None
    assert owner.timezone == TIMEZONE


async def test_tasks_are_listed_in_local_time(
    task_service: TaskService, session_factory: async_sessionmaker
) -> None:
    async with session_factory() as setup_session:
        await UserRepository(setup_session).ensure(OWNER_ID, TIMEZONE, NOW)
        await TaskRepository(setup_session).add(
            Task(
                user_id=OWNER_ID,
                title="Купить корм коту",
                due_at=datetime(2026, 8, 5, 12, 0, tzinfo=UTC),
                created_at=NOW,
            )
        )
        await TaskRepository(setup_session).add(
            Task(user_id=OWNER_ID, title="Почитать книгу", created_at=NOW)
        )
        await setup_session.commit()
    message = MessageSpy()

    await handle_tasks(message, task_service, KRASNOYARSK)  # type: ignore[arg-type]

    answer = message.answers[0]
    assert "05.08 19:00 — Купить корм коту" in answer, "UTC 12:00 is 19:00 in Krasnoyarsk"
    assert "Без срока:\n• Почитать книгу" in answer


async def test_other_users_tasks_are_not_shown(
    task_service: TaskService, session_factory: async_sessionmaker
) -> None:
    stranger_id = 222
    async with session_factory() as setup_session:
        await UserRepository(setup_session).ensure(stranger_id, TIMEZONE, NOW)
        await TaskRepository(setup_session).add(
            Task(user_id=stranger_id, title="чужая задача", created_at=NOW)
        )
        await setup_session.commit()
    message = MessageSpy(user_id=OWNER_ID)

    await handle_tasks(message, task_service, KRASNOYARSK)  # type: ignore[arg-type]

    assert message.answers == [EMPTY_LIST_TEXT]
