"""Bad model output, unusable dates and a provider in trouble — none of it crashes.

Every case is driven through `handle_message`, so what is asserted is what the
owner reads and what the database holds.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from openai import APIStatusError, APITimeoutError, OpenAIError
from sqlalchemy.ext.asyncio import AsyncSession

from graph.llm import LLMClient, LLMError, ScriptedLLMClient
from graph.nodes import (
    DUE_IN_THE_PAST_REPLY,
    DUE_TOO_FAR_REPLY,
    LLM_UNAVAILABLE_REPLY,
    UNPARSED_REPLY,
)
from graph.openrouter import BACKOFF_BASE_SECONDS, OpenRouterClient
from graph.runner import MessageHandler
from repositories.tasks import TaskRepository
from tests.conftest import NOW, OWNER_ID

Handlers = Callable[[LLMClient], MessageHandler]

VALID = {
    "intent": "create_task",
    "title": "Купить корм коту",
    "due_at": "2026-08-05T19:00:00+07:00",
}
BROKEN = "не json вовсе"


def scripted(*responses: object) -> ScriptedLLMClient:
    return ScriptedLLMClient(
        response if isinstance(response, str) else json.dumps(response) for response in responses
    )


async def reply_to(make_handler: Handlers, text: str, llm: LLMClient) -> str:
    return await make_handler(llm).handle_message(text=text, user_id=OWNER_ID, now=NOW)


def dated(due_at: datetime) -> dict[str, object]:
    return {**VALID, "due_at": due_at.isoformat()}


class TestRetryAfterInvalidOutput:
    async def test_a_broken_answer_is_retried_once_and_the_task_lands(
        self, make_handler: Handlers, session: AsyncSession
    ) -> None:
        llm = scripted(BROKEN, VALID)

        reply = await reply_to(make_handler, "купить корм коту завтра в 19", llm)

        assert [task.title for task in await TaskRepository(session).list_pending(OWNER_ID)] == [
            "Купить корм коту"
        ]
        assert "Купить корм коту" in reply
        assert len(llm.calls) == 2

    async def test_the_retry_carries_the_validation_error(self, make_handler: Handlers) -> None:
        llm = scripted(json.dumps({"intent": "buy_me_a_beer"}), VALID)

        await reply_to(make_handler, "купить корм коту завтра в 19", llm)

        first_system, _user = llm.calls[0]
        retry_system, retry_user = llm.calls[1]
        assert retry_system.startswith(first_system), "the retry keeps the original instructions"
        assert "buy_me_a_beer" in retry_system, "the model is shown what it got wrong"
        assert retry_user == "купить корм коту завтра в 19"

    async def test_two_failures_in_a_row_are_an_honest_refusal(
        self, make_handler: Handlers, session: AsyncSession
    ) -> None:
        llm = scripted(BROKEN, BROKEN)

        reply = await reply_to(make_handler, "купить корм коту завтра в 19", llm)

        assert reply == UNPARSED_REPLY
        assert await TaskRepository(session).list_pending(OWNER_ID) == []
        assert len(llm.calls) == 2, "exactly one retry, never a loop"

    async def test_a_provider_failure_is_never_retried_as_a_parse_error(
        self, make_handler: Handlers, session: AsyncSession
    ) -> None:
        class BrokenLLM:
            def __init__(self) -> None:
                self.calls = 0

            async def complete(self, *, system: str, user: str) -> str:
                self.calls += 1
                raise LLMError("429")

        llm = BrokenLLM()
        reply = await reply_to(make_handler, "купить корм коту завтра в 19", llm)

        assert reply == LLM_UNAVAILABLE_REPLY
        assert llm.calls == 1, "the client owns the backoff, the parser does not double it"
        assert await TaskRepository(session).list_pending(OWNER_ID) == []


class TestDueDateSanity:
    async def test_a_date_in_the_past_is_explained_and_stored_nowhere(
        self, make_handler: Handlers, session: AsyncSession
    ) -> None:
        llm = scripted(dated(NOW - timedelta(hours=1)))

        reply = await reply_to(make_handler, "напомни купить корм вчера", llm)

        assert reply == DUE_IN_THE_PAST_REPLY
        assert await TaskRepository(session).list_pending(OWNER_ID) == []
        assert len(llm.calls) == 1, "a well-formed wrong date is not the model's to re-answer"

    async def test_a_date_beyond_a_year_is_treated_as_a_slip(
        self, make_handler: Handlers, session: AsyncSession
    ) -> None:
        llm = scripted(dated(NOW + timedelta(days=400)))

        reply = await reply_to(make_handler, "напомни купить корм в 2027", llm)

        assert reply == DUE_TOO_FAR_REPLY
        assert await TaskRepository(session).list_pending(OWNER_ID) == []

    async def test_the_far_edge_of_the_horizon_is_still_accepted(
        self, make_handler: Handlers, session: AsyncSession
    ) -> None:
        due_at = NOW + timedelta(days=364)
        llm = scripted(dated(due_at))

        await reply_to(make_handler, "напомни купить корм через год", llm)

        assert [task.due_at for task in await TaskRepository(session).list_pending(OWNER_ID)] == [
            due_at
        ]

    async def test_an_undated_task_is_untouched_by_the_check(
        self, make_handler: Handlers, session: AsyncSession
    ) -> None:
        llm = scripted({**VALID, "due_at": None})

        await reply_to(make_handler, "купить корм коту", llm)

        assert [task.due_at for task in await TaskRepository(session).list_pending(OWNER_ID)] == [
            None
        ]

    async def test_a_stale_date_under_another_intent_is_ignored(
        self, make_handler: Handlers
    ) -> None:
        """Only create_task reads `due_at`, so an old date elsewhere refuses nothing."""
        stale = {"intent": "smalltalk", "smalltalk_reply": "Привет!", "due_at": "2020-01-01"}

        assert await reply_to(make_handler, "привет", scripted(stale)) == "Привет!"


class TestProviderBackoff:
    """The retry policy of the real client, with sleeps recorded instead of taken."""

    def request(self) -> httpx.Request:
        return httpx.Request("POST", "https://openrouter.test/chat/completions")

    def error(self, status_code: int) -> APIStatusError:
        response = httpx.Response(status_code, request=self.request())
        return APIStatusError("boom", response=response, body=None)

    def build(
        self, *failures: OpenAIError, answer: str = "{}"
    ) -> tuple[OpenRouterClient, list[float]]:
        slept: list[float] = []
        pending = list(failures)

        async def record(seconds: float) -> None:
            slept.append(seconds)

        class RetryingClient(OpenRouterClient):
            async def _request(self, *, system: str, user: str) -> str:
                if pending:
                    raise pending.pop(0)
                return answer

        client = RetryingClient(
            api_key="k", model="m", base_url="https://openrouter.test", sleep=record
        )
        return client, slept

    async def test_a_rate_limit_is_waited_out_with_growing_pauses(self) -> None:
        client, slept = self.build(self.error(429), APITimeoutError(request=self.request()))

        assert await client.complete(system="s", user="u") == "{}"
        assert slept == [BACKOFF_BASE_SECONDS, BACKOFF_BASE_SECONDS * 2]

    async def test_exhausted_attempts_become_a_temporary_unavailability(self) -> None:
        client, slept = self.build(*[self.error(503)] * 3)

        with pytest.raises(LLMError, match="after 3 attempts"):
            await client.complete(system="s", user="u")
        assert len(slept) == 2, "no pause after the last attempt"

    async def test_a_rejected_request_is_not_retried(self) -> None:
        client, slept = self.build(self.error(401))

        with pytest.raises(LLMError, match="request failed"):
            await client.complete(system="s", user="u")
        assert slept == []


def test_the_horizon_is_measured_from_now() -> None:
    """The check is pure, so it is worth pinning without a graph around it."""
    from graph.extract import DueDateRejected, ensure_due_at_is_usable
    from graph.schemas import ParsedMessage

    now = datetime(2026, 8, 4, 9, 0, tzinfo=UTC)
    parsed = ParsedMessage(intent="create_task", title="t", due_at=now)  # type: ignore[arg-type]

    with pytest.raises(DueDateRejected) as rejected:
        ensure_due_at_is_usable(parsed, now)

    assert rejected.value.past, "the current moment has no future left in it"
