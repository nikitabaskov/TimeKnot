"""The clarifying dialog, driven through `handle_message`.

The checkpointer is real SQLite in a temp file, so the restart test reopens the
same database with a brand new saver — exactly what a restarted process does.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from graph.checkpointer import open_checkpointer
from graph.llm import ScriptedLLMClient
from graph.nodes import TIME_STILL_UNCLEAR_NOTE
from graph.runner import MessageHandler
from repositories.tasks import TaskRepository
from services.tasks import TaskService
from tests.conftest import KRASNOYARSK, NOW, OWNER_ID

AMBIGUOUS = {
    "intent": "create_task",
    "title": "Позвонить маме",
    "due_at": None,
    "needs_clarification": True,
    "clarification_question": "5 утра или 5 вечера?",
}
RESOLVED = {
    "intent": "create_task",
    "title": "Позвонить маме",
    "due_at": "2026-08-04T17:00:00+07:00",
}


def scripted(*responses: object) -> ScriptedLLMClient:
    return ScriptedLLMClient(json.dumps(response) for response in responses)


@pytest.fixture
async def checkpointer(tmp_path: Path) -> AsyncIterator[object]:
    async with open_checkpointer(tmp_path / "dialog.db") as saver:
        yield saver


def build(llm: ScriptedLLMClient, task_service: TaskService, checkpointer: object):
    return MessageHandler(llm, task_service, KRASNOYARSK, checkpointer)  # type: ignore[arg-type]


async def say(handler: MessageHandler, text: str) -> str:
    return await handler.handle_message(text=text, user_id=OWNER_ID, now=NOW)


async def test_ambiguous_time_asks_instead_of_guessing(
    task_service: TaskService, checkpointer: object, session: AsyncSession
) -> None:
    handler = build(scripted(AMBIGUOUS), task_service, checkpointer)

    reply = await say(handler, "напомни позвонить маме в 5")

    assert reply == "5 утра или 5 вечера?"
    assert await TaskRepository(session).list_pending(OWNER_ID) == [], "nothing is stored yet"


async def test_the_answer_resumes_the_same_dialog(
    task_service: TaskService, checkpointer: object, session: AsyncSession
) -> None:
    handler = build(scripted(AMBIGUOUS, RESOLVED), task_service, checkpointer)
    await say(handler, "напомни позвонить маме в 5")

    reply = await say(handler, "вечера")

    stored = await TaskRepository(session).list_pending(OWNER_ID)
    assert [task.title for task in stored] == ["Позвонить маме"]
    assert stored[0].due_at == datetime(2026, 8, 4, 10, 0, tzinfo=UTC)
    assert "Позвонить маме" in reply


async def test_the_question_carries_the_original_message(
    task_service: TaskService, checkpointer: object
) -> None:
    llm = scripted(AMBIGUOUS, RESOLVED)
    handler = build(llm, task_service, checkpointer)

    await say(handler, "напомни позвонить маме в 5")
    await say(handler, "вечера")

    follow_up_prompt, _user = llm.calls[1]
    assert "напомни позвонить маме в 5" in follow_up_prompt
    assert "5 утра или 5 вечера?" in follow_up_prompt
    assert "вечера" in follow_up_prompt


async def test_the_dialog_survives_a_restart(
    task_service: TaskService, tmp_path: Path, session: AsyncSession
) -> None:
    """A new saver over the same file continues where the old process stopped."""
    dialog_db = tmp_path / "dialog.db"
    llm = scripted(AMBIGUOUS, RESOLVED)

    async with open_checkpointer(dialog_db) as first_saver:
        assert (
            await say(build(llm, task_service, first_saver), "напомни в 5")
            == "5 утра или 5 вечера?"
        )

    async with open_checkpointer(dialog_db) as second_saver:
        reply = await say(build(llm, task_service, second_saver), "вечера")

    stored = await TaskRepository(session).list_pending(OWNER_ID)
    assert [task.title for task in stored] == ["Позвонить маме"]
    assert "Позвонить маме" in reply


async def test_only_one_question_per_task(
    task_service: TaskService, checkpointer: object, session: AsyncSession
) -> None:
    """A model that stays confused does not get to ask twice — the task lands undated."""
    handler = build(scripted(AMBIGUOUS, AMBIGUOUS), task_service, checkpointer)
    await say(handler, "напомни позвонить маме в 5")

    reply = await say(handler, "ну в пять же")

    stored = await TaskRepository(session).list_pending(OWNER_ID)
    assert [(task.title, task.due_at) for task in stored] == [("Позвонить маме", None)]
    assert TIME_STILL_UNCLEAR_NOTE in reply


async def test_the_owner_can_walk_away_from_the_question(
    task_service: TaskService, checkpointer: object, session: AsyncSession
) -> None:
    """Answering with something unrelated follows the new message, it does not trap."""
    handler = build(scripted(AMBIGUOUS, {"intent": "smalltalk"}), task_service, checkpointer)
    await say(handler, "напомни позвонить маме в 5")

    reply = await say(handler, "спасибо")

    assert "smalltalk" in reply
    assert await TaskRepository(session).list_pending(OWNER_ID) == []


async def test_the_next_message_starts_a_fresh_run(
    task_service: TaskService, checkpointer: object, session: AsyncSession
) -> None:
    """Once a dialog finished, the following message is not treated as an answer."""
    handler = build(
        scripted(
            AMBIGUOUS,
            RESOLVED,
            {"intent": "create_task", "title": "Полить цветы", "due_at": None},
        ),
        task_service,
        checkpointer,
    )
    await say(handler, "напомни позвонить маме в 5")
    await say(handler, "вечера")

    await say(handler, "полить цветы")

    stored = await TaskRepository(session).list_pending(OWNER_ID)
    assert sorted(task.title for task in stored) == ["Позвонить маме", "Полить цветы"]


async def test_a_question_without_text_is_not_asked(
    task_service: TaskService, checkpointer: object, session: AsyncSession
) -> None:
    """`needs_clarification` with no question would strand the dialog, so it is ignored."""
    handler = build(
        scripted({**AMBIGUOUS, "clarification_question": None, "due_at": None}),
        task_service,
        checkpointer,
    )

    reply = await say(handler, "напомни позвонить маме в 5")

    assert [task.title for task in await TaskRepository(session).list_pending(OWNER_ID)] == [
        "Позвонить маме"
    ]
    assert "Позвонить маме" in reply
