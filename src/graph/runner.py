"""`handle_message` — the main seam of the application.

Text, user id and the current moment in; the bot's reply out, plus whatever the
graph wrote to the database. Tests drive the product through this function.
"""

from __future__ import annotations

from datetime import datetime

from graph.build import build_message_graph
from graph.llm import LLMClient


class MessageHandler:
    def __init__(self, llm: LLMClient) -> None:
        self._graph = build_message_graph(llm)

    async def handle_message(self, *, text: str, user_id: int, now: datetime) -> str:
        state = await self._graph.ainvoke({"text": text, "user_id": user_id, "now": now})
        return state["reply"]
