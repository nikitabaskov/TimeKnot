"""Turning stored tasks into the text the owner reads. Local time lives here, not deeper."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from repositories.models import Task

EMPTY_LIST_TEXT = "Список пуст."


def render_task_list(tasks: list[Task], timezone: ZoneInfo) -> str:
    if not tasks:
        return EMPTY_LIST_TEXT

    dated = [task for task in tasks if task.due_at is not None]
    undated = [task for task in tasks if task.due_at is None]

    lines: list[str] = []
    if dated:
        lines.append("Активные задачи:")
        lines += [
            f"• {task.due_at.astimezone(timezone):%d.%m %H:%M} — {task.title}" for task in dated
        ]
    if undated:
        if lines:
            lines.append("")
        lines.append("Без срока:")
        lines += [f"• {task.title}" for task in undated]
    return "\n".join(lines)
