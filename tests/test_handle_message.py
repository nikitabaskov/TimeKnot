"""The main seam: text in, bot reply out. Every branch of the graph is exercised here.

The tests assert what the user reads and what the database holds — never node
names or call order, so the graph can be rebuilt without touching them.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from graph.llm import LLMError, ScriptedLLMClient
from graph.nodes import LLM_UNAVAILABLE_REPLY, UNPARSED_REPLY
from graph.runner import MessageHandler
from repositories.tasks import TaskRepository
from repositories.users import UserRepository
from tests.conftest import NOW, OWNER_ID


def scripted(*responses: object) -> ScriptedLLMClient:
    return ScriptedLLMClient(json.dumps(response) for response in responses)


async def reply_to(text: str, llm: ScriptedLLMClient) -> str:
    return await MessageHandler(llm).handle_message(text=text, user_id=OWNER_ID, now=NOW)


async def test_create_task_branch_sees_the_task_fields() -> None:
    llm = scripted(
        {
            "intent": "create_task",
            "title": "Купить корм коту",
            "category": "покупки",
            "due_at": "2026-08-05T19:00:00+07:00",
        }
    )

    reply = await reply_to("Купить корм коту завтра в 19:00", llm)

    assert "Купить корм коту" in reply


@pytest.mark.parametrize(
    ("intent", "expected"),
    [
        ("list_tasks", "list_tasks"),
        ("complete_task", "complete_task"),
        ("smalltalk", "smalltalk"),
    ],
)
async def test_non_creating_intents_take_their_own_branch(intent: str, expected: str) -> None:
    reply = await reply_to("что угодно", scripted({"intent": intent}))

    assert expected in reply


@pytest.mark.parametrize("intent", ["list_tasks", "complete_task", "smalltalk"])
async def test_task_fields_are_ignored_outside_create_task(intent: str) -> None:
    """The model invents titles and dates for every intent; only one branch may read them."""
    llm = scripted(
        {
            "intent": intent,
            "title": "выдуманная задача",
            "category": "выдуманная категория",
            "due_at": "2026-08-05T19:00:00+07:00",
        }
    )

    reply = await reply_to("что угодно", llm)

    assert "выдуманная" not in reply
    assert "2026" not in reply


async def test_unknown_intent_is_a_parse_failure() -> None:
    reply = await reply_to("привет", scripted({"intent": "buy_me_a_beer"}))

    assert reply == UNPARSED_REPLY


async def test_malformed_json_is_a_parse_failure() -> None:
    reply = await reply_to("привет", ScriptedLLMClient(["не json вовсе"]))

    assert reply == UNPARSED_REPLY


async def test_provider_failure_is_reported_without_crashing() -> None:
    class BrokenLLM:
        async def complete(self, *, system: str, user: str) -> str:
            raise LLMError("429")

    handler = MessageHandler(BrokenLLM())

    reply = await handler.handle_message(text="привет", user_id=OWNER_ID, now=NOW)

    assert reply == LLM_UNAVAILABLE_REPLY


@pytest.mark.parametrize(
    "response",
    [
        {"intent": "list_tasks"},
        {"intent": "complete_task"},
        {"intent": "smalltalk"},
        {"intent": "create_task", "title": "Купить корм коту"},
        {"intent": "nonsense"},
    ],
)
async def test_no_branch_writes_to_the_database_yet(
    response: dict[str, str], session: AsyncSession
) -> None:
    """Creation lands in ticket 04; until then the seam must stay side-effect free."""
    await reply_to("что угодно", scripted(response))

    assert await UserRepository(session).list_all() == []
    assert await TaskRepository(session).list_pending(OWNER_ID) == []
