"""`/start` explains what the bot can do."""

from __future__ import annotations

from bot.handlers import START_TEXT, handle_start


class MessageSpy:
    def __init__(self) -> None:
        self.answers: list[str] = []

    async def answer(self, text: str) -> None:
        self.answers.append(text)


async def test_start_answers_with_capabilities() -> None:
    message = MessageSpy()

    await handle_start(message)  # type: ignore[arg-type]

    assert message.answers == [START_TEXT]
    assert "/tasks" in START_TEXT
