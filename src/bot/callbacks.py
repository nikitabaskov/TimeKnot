"""Callback handling: the two buttons under a reminder."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.keyboards import CALLBACK_PREFIX, COMPLETE_ACTION, parse_callback_data
from rendering import (
    ALREADY_CLOSED_TEXT,
    TASK_NOT_FOUND_TEXT,
    render_task_completed,
    render_task_snoozed,
)
from services.tasks import Outcome, TaskService

router = Router(name="task-buttons")


@router.callback_query(F.data.startswith(f"{CALLBACK_PREFIX}:"))
async def handle_task_button(
    callback: CallbackQuery, task_service: TaskService, timezone: ZoneInfo
) -> None:
    parsed = parse_callback_data(callback.data or "")
    if parsed is None:
        await callback.answer()
        return

    action, task_id = parsed
    if action == COMPLETE_ACTION:
        outcome, task = await task_service.complete(task_id, callback.from_user.id)
        text = render_task_completed(task) if task is not None else None
    else:
        outcome, task = await task_service.snooze(task_id, callback.from_user.id)
        text = render_task_snoozed(task, timezone) if task is not None else None

    if outcome is not Outcome.UPDATED:
        # A stale button: the task was already closed, or belongs to nobody. Say so
        # and leave the state alone.
        notice = ALREADY_CLOSED_TEXT if outcome is Outcome.ALREADY_CLOSED else TASK_NOT_FOUND_TEXT
        await callback.answer(notice)
        return

    assert text is not None
    # Replacing the text drops the keyboard with it, so the same button cannot be
    # pressed twice from the same message.
    await callback.message.edit_text(text)
    await callback.answer()
