"""The two buttons under a reminder, driven through the callback seam."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.callbacks import handle_task_button
from bot.keyboards import (
    COMPLETE_ACTION,
    SNOOZE_ACTION,
    callback_data,
    parse_callback_data,
    reminder_keyboard,
)
from rendering import ALREADY_CLOSED_TEXT, TASK_NOT_FOUND_TEXT
from repositories.models import Task, TaskStatus
from repositories.tasks import TaskRepository
from repositories.users import UserRepository
from services.reminders import ReminderService
from services.tasks import SNOOZE_STEP, TaskService
from tests.conftest import (
    KRASNOYARSK,
    NOW,
    OWNER_ID,
    TIMEZONE,
    CallbackSpy,
    PlannerSpy,
    SenderSpy,
)

DUE = NOW + timedelta(hours=2)
STRANGER_ID = 222


async def store_task(
    session_factory: async_sessionmaker,
    *,
    title: str = "Купить корм коту",
    due_at: object = DUE,
    status: TaskStatus = TaskStatus.PENDING,
    user_id: int = OWNER_ID,
    reminder_sent_at: object = None,
) -> int:
    async with session_factory() as session:
        await UserRepository(session).ensure(user_id, TIMEZONE, NOW)
        task = await TaskRepository(session).add(
            Task(
                user_id=user_id,
                title=title,
                due_at=due_at,
                status=status,
                created_at=NOW,
                reminder_sent_at=reminder_sent_at,
            )
        )
        await session.commit()
        return task.id


async def press(task_service: TaskService, action: str, task_id: int, **kwargs) -> CallbackSpy:
    callback = CallbackSpy(callback_data(action, task_id), **kwargs)
    await handle_task_button(callback, task_service, KRASNOYARSK)  # type: ignore[arg-type]
    return callback


def test_the_reminder_keyboard_has_exactly_two_buttons() -> None:
    keyboard = reminder_keyboard(7)

    (row,) = keyboard.inline_keyboard
    assert [button.text for button in row] == ["Завершено", "Отложить на 1 час"]
    assert [parse_callback_data(button.callback_data) for button in row] == [
        (COMPLETE_ACTION, 7),
        (SNOOZE_ACTION, 7),
    ]


async def test_a_reminder_goes_out_carrying_its_task_id(
    session_factory: async_sessionmaker, sender: SenderSpy
) -> None:
    task_id = await store_task(session_factory, due_at=NOW - timedelta(minutes=5))

    await ReminderService(session_factory, sender).dispatch_due(NOW)

    assert sender.task_ids == [task_id], "the transport needs it to build the keyboard"


async def test_completing_closes_the_task_and_strips_the_buttons(
    task_service: TaskService, session_factory: async_sessionmaker, session: AsyncSession
) -> None:
    task_id = await store_task(session_factory)

    callback = await press(task_service, COMPLETE_ACTION, task_id)

    stored = await TaskRepository(session).get(task_id)
    assert stored is not None
    assert stored.status == TaskStatus.DONE
    assert callback.message.edits == ["Завершено: «Купить корм коту»"]


async def test_a_completed_task_leaves_the_list(
    task_service: TaskService, session_factory: async_sessionmaker
) -> None:
    task_id = await store_task(session_factory)

    await press(task_service, COMPLETE_ACTION, task_id)

    assert await task_service.list_active(OWNER_ID) == []


async def test_a_completed_task_produces_no_reminder(
    task_service: TaskService, session_factory: async_sessionmaker, sender: SenderSpy
) -> None:
    task_id = await store_task(session_factory)

    await press(task_service, COMPLETE_ACTION, task_id)
    await ReminderService(session_factory, sender).dispatch_due(DUE + timedelta(minutes=1))

    assert sender.sent == []


async def test_snoozing_moves_the_moment_by_one_hour(
    task_service: TaskService, session_factory: async_sessionmaker, session: AsyncSession
) -> None:
    task_id = await store_task(session_factory)

    callback = await press(task_service, SNOOZE_ACTION, task_id)

    stored = await TaskRepository(session).get(task_id)
    assert stored is not None
    assert stored.due_at == DUE + SNOOZE_STEP
    assert stored.status == TaskStatus.PENDING, "snoozing does not close anything"
    # DUE is 11:00 UTC; an hour later is 12:00 UTC, which is 19:00 in Krasnoyarsk.
    assert callback.message.edits == ["Отложено: «Купить корм коту»\nНапомню 04.08 в 19:00."]


async def test_snoozing_re_arms_the_timer(
    task_service: TaskService, session_factory: async_sessionmaker, planner: PlannerSpy
) -> None:
    task_id = await store_task(session_factory)

    await press(task_service, SNOOZE_ACTION, task_id)

    assert planner.scheduled == [(task_id, DUE + SNOOZE_STEP)]


async def test_a_snoozed_reminder_is_actually_sent_again(
    task_service: TaskService, session_factory: async_sessionmaker, sender: SenderSpy
) -> None:
    """Snoozing must clear `reminder_sent_at`, or dispatch would treat it as delivered."""
    task_id = await store_task(session_factory, reminder_sent_at=DUE)

    await press(task_service, SNOOZE_ACTION, task_id)
    sent = await ReminderService(session_factory, sender).dispatch_due(
        DUE + SNOOZE_STEP + timedelta(seconds=1)
    )

    assert [reminder.task_id for reminder in sent] == [task_id]


async def test_snoozing_an_overdue_reminder_waits_a_full_hour(
    session_factory: async_sessionmaker, planner: PlannerSpy, clock: object
) -> None:
    """After downtime a caught-up reminder is hours old; "again in an hour" means from now."""
    long_overdue = NOW - timedelta(hours=5)
    task_id = await store_task(session_factory, due_at=long_overdue)
    service = TaskService(session_factory, clock, TIMEZONE, planner=planner)  # type: ignore[arg-type]

    await press(service, SNOOZE_ACTION, task_id)

    assert planner.scheduled == [(task_id, NOW + SNOOZE_STEP)]


@pytest.mark.parametrize("action", [COMPLETE_ACTION, SNOOZE_ACTION])
async def test_pressing_a_stale_button_changes_nothing(
    task_service: TaskService,
    session_factory: async_sessionmaker,
    session: AsyncSession,
    planner: PlannerSpy,
    action: str,
) -> None:
    task_id = await store_task(session_factory)
    await press(task_service, COMPLETE_ACTION, task_id)
    planner.scheduled.clear()

    callback = await press(task_service, action, task_id)

    stored = await TaskRepository(session).get(task_id)
    assert stored is not None
    assert stored.status == TaskStatus.DONE
    assert stored.due_at == DUE, "a stale snooze must not move the moment"
    assert callback.answers == [ALREADY_CLOSED_TEXT]
    assert callback.message.edits == []
    assert planner.scheduled == []


@pytest.mark.parametrize("action", [COMPLETE_ACTION, SNOOZE_ACTION])
async def test_someone_elses_task_is_not_touchable(
    task_service: TaskService,
    session_factory: async_sessionmaker,
    session: AsyncSession,
    action: str,
) -> None:
    task_id = await store_task(session_factory, user_id=STRANGER_ID)

    callback = await press(task_service, action, task_id)

    stored = await TaskRepository(session).get(task_id)
    assert stored is not None
    assert stored.status == TaskStatus.PENDING
    assert callback.answers == [TASK_NOT_FOUND_TEXT]


async def test_a_missing_task_is_reported_not_crashed(task_service: TaskService) -> None:
    callback = await press(task_service, COMPLETE_ACTION, 999)

    assert callback.answers == [TASK_NOT_FOUND_TEXT]


async def test_unrecognised_callback_data_is_ignored(task_service: TaskService) -> None:
    callback = CallbackSpy("task:explode:7")

    await handle_task_button(callback, task_service, KRASNOYARSK)  # type: ignore[arg-type]

    assert callback.answers == [None]
    assert callback.message.edits == []
