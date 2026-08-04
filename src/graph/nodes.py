"""Graph nodes.

Only the parse node is real in this ticket. The four intent nodes are stubs:
ticket 04 fills in task creation, ticket 09 the list, complete and smalltalk
branches. They exist now so the branching itself can be tested.
"""

from __future__ import annotations

from pydantic import ValidationError

from graph.llm import LLMClient, LLMError
from graph.schemas import Intent, ParsedMessage
from graph.state import DialogState, StateUpdate

# Expanded in ticket 04, where the local date, time and weekday are added.
SYSTEM_PROMPT = (
    "Ты разбираешь сообщения пользователя русскоязычного ассистента задач. "
    "Верни JSON с полями intent (create_task, list_tasks, complete_task, smalltalk), "
    "title, category, due_at."
)

UNPARSED_REPLY = "Не смог разобрать сообщение. Попробуй сформулировать иначе."
LLM_UNAVAILABLE_REPLY = "Сейчас не могу обработать сообщение — модель недоступна. Попробуй позже."

UNPARSED_ROUTE = "unparsed"


def make_parse_node(llm: LLMClient):
    """The node closes over the LLM client; LangGraph only ever passes `state`."""

    async def parse(state: DialogState) -> StateUpdate:
        try:
            raw = await llm.complete(system=SYSTEM_PROMPT, user=state["text"])
        except LLMError:
            return {"parsed": None, "reply": LLM_UNAVAILABLE_REPLY}

        try:
            # Ticket 04 adds the single retry with the validation error appended.
            parsed = ParsedMessage.model_validate_json(raw)
        except ValidationError:
            return {"parsed": None, "reply": UNPARSED_REPLY}

        return {"parsed": parsed}

    return parse


def route_by_intent(state: DialogState) -> str:
    parsed = state.get("parsed")
    if parsed is None:
        return UNPARSED_ROUTE
    return parsed.intent.value


async def create_task(state: DialogState) -> StateUpdate:
    parsed = state.get("parsed")
    assert parsed is not None, "the create_task branch is only reachable with a parsed message"
    return {"reply": f"[stub create_task] {parsed.title} / {parsed.due_at}"}


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
