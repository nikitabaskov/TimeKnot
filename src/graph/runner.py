"""`handle_message` — the main seam of the application.

Text, user id and the current moment in; the bot's reply out, plus whatever the
graph wrote to the database. Tests drive the product through this function.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from graph.build import build_message_graph
from graph.llm import LLMClient
from services.tasks import TaskService


class MessageHandler:
    def __init__(
        self,
        llm: LLMClient,
        task_service: TaskService,
        timezone: ZoneInfo,
        checkpointer: BaseCheckpointSaver | None = None,
    ) -> None:
        self._graph = build_message_graph(llm, task_service, timezone, checkpointer)
        self._checkpointer = checkpointer

    async def handle_message(self, *, text: str, user_id: int, now: datetime) -> str:
        # One thread per chat. Without a checkpointer there is no state to resume
        # and every message starts a fresh run.
        config = {"configurable": {"thread_id": str(user_id)}}

        if await self._is_awaiting_answer(config):
            # The message answers a question the bot asked, possibly days and one
            # restart ago. The graph picks up inside the node that asked.
            state = await self._graph.ainvoke(Command(resume=text), config=config)
        else:
            state = await self._graph.ainvoke(
                {"text": text, "user_id": user_id, "now": now}, config=config
            )

        if state.get("__interrupt__"):
            return state["__interrupt__"][0].value
        return state["reply"]

    async def _is_awaiting_answer(self, config: dict) -> bool:
        if self._checkpointer is None:
            return False
        snapshot = await self._graph.aget_state(config)
        return bool(snapshot.next)
