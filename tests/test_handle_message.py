"""The main seam: text in, bot reply out. Every branch of the graph is exercised here.

The tests assert what the user reads and what the database holds — never node
names or call order, so the graph can be rebuilt without touching them.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from graph.llm import LLMClient, LLMError, ScriptedLLMClient
from graph.nodes import (
    DEFAULT_SMALLTALK_REPLY,
    LLM_UNAVAILABLE_REPLY,
    NO_TITLE_REPLY,
    UNPARSED_REPLY,
)
from graph.runner import MessageHandler
from rendering import EMPTY_LIST_TEXT, NOTHING_TO_CLOSE_TEXT, render_task_list
from repositories.models import TaskStatus
from repositories.tasks import TaskRepository
from repositories.users import UserRepository
from tests.conftest import KRASNOYARSK, NOW, OWNER_ID

Handlers = Callable[[LLMClient], MessageHandler]


def scripted(*responses: object) -> ScriptedLLMClient:
    return ScriptedLLMClient(json.dumps(response) for response in responses)


async def reply_to(make_handler: Handlers, text: str, llm: LLMClient) -> str:
    return await make_handler(llm).handle_message(text=text, user_id=OWNER_ID, now=NOW)


async def test_task_with_a_deadline_is_stored_in_utc(
    make_handler: Handlers, session: AsyncSession
) -> None:
    llm = scripted(
        {
            "intent": "create_task",
            "title": "Купить корм коту",
            "category": "покупки",
            "due_at": "2026-08-05T19:00:00+07:00",
        }
    )

    reply = await reply_to(make_handler, "Купить корм коту завтра в 19:00", llm)

    stored = await TaskRepository(session).list_pending(OWNER_ID)
    assert len(stored) == 1
    assert stored[0].title == "Купить корм коту"
    assert stored[0].category == "покупки"
    assert stored[0].due_at == datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
    assert stored[0].status == TaskStatus.PENDING
    assert "Купить корм коту" in reply
    assert "05.08 в 19:00" in reply, "the confirmation shows local time"


async def test_creating_a_dated_task_arms_a_timer(make_handler: Handlers, planner) -> None:
    llm = scripted(
        {"intent": "create_task", "title": "Проверить PR", "due_at": "2026-08-05T19:00:00+07:00"},
        {"intent": "create_task", "title": "Почитать книгу", "due_at": None},
    )

    await reply_to(make_handler, "напомни проверить PR завтра в 19", llm)
    await reply_to(make_handler, "почитать книгу", llm)

    assert [due_at for _task_id, due_at in planner.scheduled] == [
        datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
    ], "an undated task never reaches the scheduler"


async def test_task_without_a_time_gets_no_deadline(
    make_handler: Handlers, session: AsyncSession
) -> None:
    llm = scripted({"intent": "create_task", "title": "Почитать книгу", "due_at": None})

    reply = await reply_to(make_handler, "почитать книгу", llm)

    stored = await TaskRepository(session).list_pending(OWNER_ID)
    assert [task.due_at for task in stored] == [None]
    assert "Почитать книгу" in reply
    assert "Без срока" in reply


async def test_naive_iso_from_the_model_is_read_as_local_time(
    make_handler: Handlers, session: AsyncSession
) -> None:
    """The prompt asks for an offset; models drop it often enough to matter."""
    llm = scripted(
        {"intent": "create_task", "title": "Проверить PR", "due_at": "2026-08-04T17:00:00"}
    )

    await reply_to(make_handler, "напомни проверить PR через час", llm)

    stored = await TaskRepository(session).list_pending(OWNER_ID)
    assert stored[0].due_at == datetime(2026, 8, 4, 10, 0, tzinfo=UTC), "17:00 local is 10:00 UTC"


async def test_json_wrapped_in_a_code_fence_is_accepted(
    make_handler: Handlers, session: AsyncSession
) -> None:
    fenced = '```json\n{"intent": "create_task", "title": "Полить цветы"}\n```'

    await reply_to(make_handler, "полить цветы", ScriptedLLMClient([fenced]))

    stored = await TaskRepository(session).list_pending(OWNER_ID)
    assert [task.title for task in stored] == ["Полить цветы"]


async def test_created_task_shows_up_in_the_list(
    make_handler: Handlers, session: AsyncSession
) -> None:
    llm = scripted(
        {
            "intent": "create_task",
            "title": "Купить корм коту",
            "due_at": "2026-08-05T19:00:00+07:00",
        },
        {"intent": "create_task", "title": "Почитать книгу", "due_at": None},
    )
    await reply_to(make_handler, "купить корм коту завтра в 19", llm)
    await reply_to(make_handler, "почитать книгу", llm)

    listed = render_task_list(await TaskRepository(session).list_pending(OWNER_ID), KRASNOYARSK)

    assert "05.08 19:00 — Купить корм коту" in listed
    assert "Без срока:\n• Почитать книгу" in listed


async def test_create_without_a_title_creates_nothing(
    make_handler: Handlers, session: AsyncSession
) -> None:
    reply = await reply_to(make_handler, "э", scripted({"intent": "create_task", "title": None}))

    assert reply == NO_TITLE_REPLY
    assert await TaskRepository(session).list_pending(OWNER_ID) == []


@pytest.mark.parametrize(
    ("intent", "expected"),
    [
        ("list_tasks", EMPTY_LIST_TEXT),
        ("complete_task", NOTHING_TO_CLOSE_TEXT),
        ("smalltalk", DEFAULT_SMALLTALK_REPLY),
    ],
)
async def test_non_creating_intents_take_their_own_branch(
    make_handler: Handlers, intent: str, expected: str
) -> None:
    reply = await reply_to(make_handler, "что угодно", scripted({"intent": intent}))

    assert reply == expected


@pytest.mark.parametrize("intent", ["list_tasks", "complete_task", "smalltalk"])
async def test_task_fields_are_ignored_outside_create_task(
    make_handler: Handlers, intent: str, session: AsyncSession
) -> None:
    """The model invents titles and dates for every intent; only one branch may read them."""
    llm = scripted(
        {
            "intent": intent,
            "title": "выдуманная задача",
            "category": "выдуманная категория",
            "due_at": "2026-08-05T19:00:00+07:00",
        }
    )

    reply = await reply_to(make_handler, "что угодно", llm)

    assert "выдуманная" not in reply
    assert "2026" not in reply
    assert await TaskRepository(session).list_pending(OWNER_ID) == []


async def test_unknown_intent_is_a_parse_failure(make_handler: Handlers) -> None:
    unknown = {"intent": "buy_me_a_beer"}

    reply = await reply_to(make_handler, "привет", scripted(unknown, unknown))

    assert reply == UNPARSED_REPLY


async def test_malformed_json_is_a_parse_failure(
    make_handler: Handlers, session: AsyncSession
) -> None:
    reply = await reply_to(make_handler, "привет", ScriptedLLMClient(["не json", "тоже не json"]))

    assert reply == UNPARSED_REPLY
    assert await UserRepository(session).list_all() == [], "a failed parse touches nothing"


async def test_provider_failure_is_reported_without_crashing(
    make_handler: Handlers, session: AsyncSession
) -> None:
    class BrokenLLM:
        async def complete(self, *, system: str, user: str) -> str:
            raise LLMError("429")

    reply = await reply_to(make_handler, "привет", BrokenLLM())

    assert reply == LLM_UNAVAILABLE_REPLY
    assert await TaskRepository(session).list_pending(OWNER_ID) == []


async def test_prompt_carries_the_current_local_moment(make_handler: Handlers) -> None:
    llm = scripted({"intent": "smalltalk"})

    await reply_to(make_handler, "привет", llm)

    system, user = llm.calls[0]
    assert "2026-08-04 16:00" in system, "NOW is 09:00 UTC, which is 16:00 in Krasnoyarsk"
    assert "вторник" in system
    assert "+07:00" in system
    assert user == "привет"
