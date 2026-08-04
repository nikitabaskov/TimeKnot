"""Viewing and closing tasks in plain text, through `handle_message`."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from graph.checkpointer import open_checkpointer
from graph.llm import ScriptedLLMClient
from graph.runner import MessageHandler
from rendering import (
    CHOICE_NOT_UNDERSTOOD_TEXT,
    EMPTY_LIST_TEXT,
    NOTHING_TO_CLOSE_TEXT,
    render_task_list,
)
from repositories.models import TaskStatus
from repositories.tasks import TaskRepository
from services.matching import find_matches
from services.tasks import TaskService
from tests.conftest import KRASNOYARSK, NOW, OWNER_ID

DUE = NOW + timedelta(hours=3)


def scripted(*responses: object) -> ScriptedLLMClient:
    return ScriptedLLMClient(json.dumps(response) for response in responses)


@pytest.fixture
async def checkpointer(tmp_path: Path) -> AsyncIterator[object]:
    async with open_checkpointer(tmp_path / "dialog.db") as saver:
        yield saver


def build(llm: ScriptedLLMClient, task_service: TaskService, checkpointer: object = None):
    return MessageHandler(llm, task_service, KRASNOYARSK, checkpointer)  # type: ignore[arg-type]


async def say(handler: MessageHandler, text: str) -> str:
    return await handler.handle_message(text=text, user_id=OWNER_ID, now=NOW)


async def seed(task_service: TaskService, *titles: str) -> dict[str, int]:
    ids = {}
    for title in titles:
        task = await task_service.create_task(OWNER_ID, title=title)
        ids[title] = task.id
    return ids


async def status_of(session: AsyncSession, task_id: int) -> TaskStatus:
    task = await TaskRepository(session).get(task_id)
    assert task is not None
    return task.status


async def test_asking_in_words_gives_the_same_list_as_the_command(
    task_service: TaskService,
) -> None:
    await seed(task_service, "Купить корм коту")
    await task_service.create_task(OWNER_ID, title="Проверить PR", due_at=DUE)
    handler = build(scripted({"intent": "list_tasks"}), task_service)

    reply = await say(handler, "что на сегодня?")

    assert reply == render_task_list(await task_service.list_active(OWNER_ID), KRASNOYARSK)
    assert "Проверить PR" in reply
    assert "Без срока:\n• Купить корм коту" in reply


async def test_the_list_is_empty_when_nothing_is_open(task_service: TaskService) -> None:
    handler = build(scripted({"intent": "list_tasks"}), task_service)

    assert await say(handler, "что на сегодня?") == EMPTY_LIST_TEXT


async def test_closing_by_words_marks_the_task_done(
    task_service: TaskService, session: AsyncSession
) -> None:
    ids = await seed(task_service, "Купить корм коту", "Проверить PR")
    handler = build(
        scripted({"intent": "complete_task", "target": "корм коту"}),
        task_service,
    )

    reply = await say(handler, "сделал корм коту")

    assert await status_of(session, ids["Купить корм коту"]) == TaskStatus.DONE
    assert await status_of(session, ids["Проверить PR"]) == TaskStatus.PENDING
    assert reply == "Завершено: «Купить корм коту»"


async def test_cancelling_is_distinguishable_from_completing(
    task_service: TaskService, session: AsyncSession
) -> None:
    ids = await seed(task_service, "Купить корм коту")
    handler = build(
        scripted({"intent": "complete_task", "target": "корм коту", "resolution": "cancelled"}),
        task_service,
    )

    reply = await say(handler, "корм коту уже не нужен")

    assert await status_of(session, ids["Купить корм коту"]) == TaskStatus.CANCELLED
    assert reply == "Отменено: «Купить корм коту»"
    assert await task_service.list_active(OWNER_ID) == [], "a cancelled task leaves the list"


async def test_nothing_matching_is_reported_and_closes_nothing(
    task_service: TaskService, session: AsyncSession
) -> None:
    await seed(task_service, "Купить корм коту")
    handler = build(
        scripted({"intent": "complete_task", "target": "починить велосипед"}), task_service
    )

    reply = await say(handler, "починил велосипед")

    assert reply == NOTHING_TO_CLOSE_TEXT
    assert len(await task_service.list_active(OWNER_ID)) == 1


async def test_several_matches_ask_instead_of_guessing(
    task_service: TaskService, checkpointer: object
) -> None:
    await seed(task_service, "Позвонить маме", "Позвонить врачу")
    handler = build(
        scripted({"intent": "complete_task", "target": "позвонить"}), task_service, checkpointer
    )

    reply = await say(handler, "позвонил")

    assert reply == "Какую именно закрыть?\n1. Позвонить маме\n2. Позвонить врачу"
    assert len(await task_service.list_active(OWNER_ID)) == 2, "nothing is closed while asking"


async def test_the_choice_closes_exactly_one_task(
    task_service: TaskService, checkpointer: object
) -> None:
    await seed(task_service, "Позвонить маме", "Позвонить врачу")
    handler = build(
        scripted({"intent": "complete_task", "target": "позвонить"}), task_service, checkpointer
    )
    await say(handler, "позвонил")

    reply = await say(handler, "2")

    assert reply == "Завершено: «Позвонить врачу»"
    assert [task.title for task in await task_service.list_active(OWNER_ID)] == ["Позвонить маме"]


async def test_the_choice_can_be_given_in_words(
    task_service: TaskService, checkpointer: object
) -> None:
    await seed(task_service, "Позвонить маме", "Позвонить врачу")
    handler = build(
        scripted({"intent": "complete_task", "target": "позвонить"}), task_service, checkpointer
    )
    await say(handler, "позвонил")

    reply = await say(handler, "врачу")

    assert reply == "Завершено: «Позвонить врачу»"


async def test_an_unusable_choice_closes_nothing(
    task_service: TaskService, checkpointer: object
) -> None:
    await seed(task_service, "Позвонить маме", "Позвонить врачу")
    handler = build(
        scripted({"intent": "complete_task", "target": "позвонить"}), task_service, checkpointer
    )
    await say(handler, "позвонил")

    reply = await say(handler, "не помню")

    assert reply == CHOICE_NOT_UNDERSTOOD_TEXT
    assert len(await task_service.list_active(OWNER_ID)) == 2


async def test_smalltalk_answers_briefly_and_stores_nothing(
    task_service: TaskService, session: AsyncSession
) -> None:
    handler = build(
        scripted({"intent": "smalltalk", "smalltalk_reply": "Привет! Чем помочь?"}), task_service
    )

    reply = await say(handler, "привет")

    assert reply == "Привет! Чем помочь?"
    assert await TaskRepository(session).list_pending(OWNER_ID) == []


async def test_a_closed_task_gives_no_reminder_and_leaves_the_list(
    task_service: TaskService, session: AsyncSession
) -> None:
    await task_service.create_task(OWNER_ID, title="Купить корм коту", due_at=DUE)
    handler = build(scripted({"intent": "complete_task", "target": "корм коту"}), task_service)

    await say(handler, "купил корм")

    assert await task_service.list_active(OWNER_ID) == []
    assert await TaskRepository(session).list_due(DUE + timedelta(minutes=1)) == []


class TestMatching:
    """The matcher itself: Russian endings differ, the meaning does not."""

    def make(self, *titles: str) -> list:
        from repositories.models import Task

        return [Task(id=index, user_id=OWNER_ID, title=title) for index, title in enumerate(titles)]

    def test_inflected_forms_still_match(self) -> None:
        tasks = self.make("Полить цветы")

        assert [task.title for task in find_matches("полил цветок", tasks)] == ["Полить цветы"]

    def test_the_best_match_wins_over_a_weaker_one(self) -> None:
        tasks = self.make("Купить корм коту", "Купить хлеб")

        assert [task.title for task in find_matches("купил корм коту", tasks)] == [
            "Купить корм коту"
        ]

    def test_a_genuine_tie_returns_both(self) -> None:
        tasks = self.make("Позвонить маме", "Позвонить врачу")

        assert len(find_matches("позвонить", tasks)) == 2

    def test_filler_words_alone_match_nothing(self) -> None:
        tasks = self.make("Купить корм коту")

        assert find_matches("сделал", tasks) == []
