"""Turning stored tasks into the text the owner reads. Local time lives here, not deeper."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from repositories.models import Task

EMPTY_LIST_TEXT = "Список пуст."
NO_DUE_DATE_TEXT = "Без срока."


def render_task_created(task: Task, timezone: ZoneInfo) -> str:
    """Confirmation. Shows what was understood so a misreading is caught immediately."""
    when = (
        NO_DUE_DATE_TEXT
        if task.due_at is None
        else f"Напомню {task.due_at.astimezone(timezone):%d.%m в %H:%M}."
    )
    return f"Записал: «{task.title}»\n{when}"


def render_task_list(tasks: list[Task], timezone: ZoneInfo) -> str:
    if not tasks:
        return EMPTY_LIST_TEXT

    dated = [(task.due_at, task.title) for task in tasks if task.due_at is not None]
    undated = [task.title for task in tasks if task.due_at is None]

    lines: list[str] = []
    if dated:
        lines.append("Активные задачи:")
        lines += [
            f"• {due_at.astimezone(timezone):%d.%m %H:%M} — {title}" for due_at, title in dated
        ]
    if undated:
        if lines:
            lines.append("")
        lines.append("Без срока:")
        lines += [f"• {title}" for title in undated]
    return "\n".join(lines)
