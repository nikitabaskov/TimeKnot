"""Inline keyboards and the callback payloads they carry."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

CALLBACK_PREFIX = "task"
COMPLETE_ACTION = "done"
SNOOZE_ACTION = "snooze"

COMPLETE_LABEL = "Завершено"
SNOOZE_LABEL = "Отложить на 1 час"


def callback_data(action: str, task_id: int) -> str:
    return f"{CALLBACK_PREFIX}:{action}:{task_id}"


def parse_callback_data(data: str) -> tuple[str, int] | None:
    """Return (action, task_id), or None for anything this module did not produce."""
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != CALLBACK_PREFIX:
        return None
    action, raw_id = parts[1], parts[2]
    if action not in (COMPLETE_ACTION, SNOOZE_ACTION) or not raw_id.isdigit():
        return None
    return action, int(raw_id)


def reminder_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=COMPLETE_LABEL, callback_data=callback_data(COMPLETE_ACTION, task_id)
                ),
                InlineKeyboardButton(
                    text=SNOOZE_LABEL, callback_data=callback_data(SNOOZE_ACTION, task_id)
                ),
            ]
        ]
    )
