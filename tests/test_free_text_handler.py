"""The aiogram handler is a thin wrapper: it hands the seam text, user id and now."""

from __future__ import annotations

import json

from aiogram.types import Message, User

from bot.handlers import handle_free_text, router
from graph.llm import ScriptedLLMClient
from tests.conftest import NOW, OWNER_ID, FixedClock, MessageSpy


async def test_handler_passes_the_message_through_the_seam(make_handler) -> None:
    llm = ScriptedLLMClient([json.dumps({"intent": "smalltalk"})])
    message = MessageSpy()

    await handle_free_text(message, make_handler(llm), FixedClock())  # type: ignore[arg-type]

    assert message.answers == ["[stub smalltalk]"]
    _system, user_prompt = llm.calls[0]
    assert user_prompt == "test message"


async def test_the_seam_receives_the_clock_moment() -> None:
    seen: dict[str, object] = {}

    class RecordingHandler:
        async def handle_message(self, *, text: str, user_id: int, now: object) -> str:
            seen.update(text=text, user_id=user_id, now=now)
            return "ok"

    await handle_free_text(MessageSpy(), RecordingHandler(), FixedClock())  # type: ignore[arg-type]

    assert seen == {"text": "test message", "user_id": OWNER_ID, "now": NOW}


def message_with(text: str) -> Message:
    return Message.model_construct(
        message_id=1, from_user=User(id=OWNER_ID, is_bot=False, first_name="t"), text=text
    )


async def test_commands_are_not_swallowed_by_the_free_text_handler() -> None:
    text_handler = next(
        handler for handler in router.message.handlers if handler.callback is handle_free_text
    )

    accepts_command, _ = await text_handler.check(message_with("/tasks"))
    accepts_plain_text, _ = await text_handler.check(message_with("купить корм коту"))

    assert not accepts_command
    assert accepts_plain_text
