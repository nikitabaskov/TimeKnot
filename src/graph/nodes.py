"""Graph nodes.

`parse` and `create_task` are real. The other three intent branches are still
stubs — ticket 09 fills in list, complete and smalltalk.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

from langgraph.types import interrupt
from pydantic import ValidationError

from graph.extract import extract, extract_after_clarification
from graph.llm import LLMClient, LLMError
from graph.schemas import Intent
from graph.state import DialogState, StateUpdate
from rendering import render_task_created
from services.tasks import TaskService

UNPARSED_REPLY = "Не смог разобрать сообщение. Попробуй сформулировать иначе."
LLM_UNAVAILABLE_REPLY = "Сейчас не могу обработать сообщение — модель недоступна. Попробуй позже."
NO_TITLE_REPLY = "Не понял, что именно записать. Попробуй сформулировать иначе."
TIME_STILL_UNCLEAR_NOTE = "Со временем так и не разобрался — записал без срока."

UNPARSED_ROUTE = "unparsed"
CLARIFY_ROUTE = "clarify"


def make_parse_node(llm: LLMClient, timezone: ZoneInfo):
    """The node closes over its dependencies; LangGraph only ever passes `state`."""

    async def parse(state: DialogState) -> StateUpdate:
        try:
            parsed = await extract(llm, text=state["text"], now=state["now"], timezone=timezone)
        except LLMError:
            return {"parsed": None, "reply": LLM_UNAVAILABLE_REPLY}
        except ValidationError:
            # Ticket 10 adds the single retry with the validation error appended.
            return {"parsed": None, "reply": UNPARSED_REPLY}

        return {"parsed": parsed}

    return parse


def route_by_intent(state: DialogState) -> str:
    parsed = state.get("parsed")
    if parsed is None:
        return UNPARSED_ROUTE
    if parsed.needs_clarification and not state.get("clarified"):
        return CLARIFY_ROUTE
    return parsed.intent.value


def make_clarify_node(llm: LLMClient, timezone: ZoneInfo):
    async def clarify(state: DialogState) -> StateUpdate:
        parsed = state.get("parsed")
        assert parsed is not None and parsed.clarification_question is not None

        # Halts the graph. The checkpointer holds everything above; the next
        # message from the owner arrives here as the resume value.
        answer = interrupt(parsed.clarification_question)

        try:
            clarified = await extract_after_clarification(
                llm,
                original=state["text"],
                question=parsed.clarification_question,
                answer=str(answer),
                now=state["now"],
                timezone=timezone,
            )
        except LLMError:
            return {"parsed": None, "clarified": True, "reply": LLM_UNAVAILABLE_REPLY}
        except ValidationError:
            return {"parsed": None, "clarified": True, "reply": UNPARSED_REPLY}

        return {"parsed": clarified, "clarified": True}

    return clarify


def make_create_task_node(task_service: TaskService, timezone: ZoneInfo):
    async def create_task(state: DialogState) -> StateUpdate:
        parsed = state.get("parsed")
        assert parsed is not None, "this branch is only reachable with a parsed message"
        if not parsed.title:
            return {"reply": NO_TITLE_REPLY}

        task = await task_service.create_task(
            state["user_id"],
            title=parsed.title,
            category=parsed.category,
            due_at=parsed.due_at,
        )
        reply = render_task_created(task, timezone)
        if task.due_at is None and state.get("clarified"):
            # One question was already spent and the time is still unclear.
            reply = f"{reply}\n{TIME_STILL_UNCLEAR_NOTE}"
        return {"reply": reply}

    return create_task


async def list_tasks(state: DialogState) -> StateUpdate:
    return {"reply": "[stub list_tasks]"}


async def complete_task(state: DialogState) -> StateUpdate:
    return {"reply": "[stub complete_task]"}


async def smalltalk(state: DialogState) -> StateUpdate:
    return {"reply": "[stub smalltalk]"}


async def unparsed(state: DialogState) -> StateUpdate:
    # The parse node already wrote the reply; this node only terminates the branch.
    return {}


# Node names double as the routing keys returned by route_by_intent.
BRANCH_NODES = [intent.value for intent in Intent] + [UNPARSED_ROUTE]
ROUTES = BRANCH_NODES + [CLARIFY_ROUTE]
