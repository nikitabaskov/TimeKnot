"""Graph nodes: one per intent, plus the parse, clarify and unparsed branches."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from langgraph.types import interrupt
from pydantic import ValidationError

from graph.extract import extract, extract_after_clarification
from graph.llm import LLMClient, LLMError
from graph.schemas import Intent, Resolution
from graph.state import DialogState, StateUpdate
from rendering import (
    CHOICE_NOT_UNDERSTOOD_TEXT,
    NOTHING_TO_CLOSE_TEXT,
    render_completion_choice,
    render_task_completed,
    render_task_created,
    render_task_list,
)
from repositories.models import Task, TaskStatus
from services.matching import find_matches
from services.tasks import Outcome, TaskService

UNPARSED_REPLY = "Не смог разобрать сообщение. Попробуй сформулировать иначе."
LLM_UNAVAILABLE_REPLY = "Сейчас не могу обработать сообщение — модель недоступна. Попробуй позже."
NO_TITLE_REPLY = "Не понял, что именно записать. Попробуй сформулировать иначе."
TIME_STILL_UNCLEAR_NOTE = "Со временем так и не разобрался — записал без срока."
DEFAULT_SMALLTALK_REPLY = "На связи. Напиши, что нужно сделать — запишу."

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


def make_list_tasks_node(task_service: TaskService, timezone: ZoneInfo):
    async def list_tasks(state: DialogState) -> StateUpdate:
        # The same call `/tasks` makes, so both routes always agree.
        tasks = await task_service.list_active(state["user_id"])
        return {"reply": render_task_list(tasks, timezone)}

    return list_tasks


def make_complete_task_node(task_service: TaskService):
    async def complete_task(state: DialogState) -> StateUpdate:
        parsed = state.get("parsed")
        assert parsed is not None
        user_id = state["user_id"]
        status = (
            TaskStatus.CANCELLED if parsed.resolution is Resolution.CANCELLED else TaskStatus.DONE
        )

        candidates = find_matches(
            parsed.target or state["text"], await task_service.list_active(user_id)
        )
        if not candidates:
            return {"reply": NOTHING_TO_CLOSE_TEXT}

        if len(candidates) > 1:
            # A tie is never resolved by guessing: closing the wrong task is worse
            # than one extra question.
            chosen = pick_candidate(
                str(interrupt(render_completion_choice(candidates))), candidates
            )
            if chosen is None:
                return {"reply": CHOICE_NOT_UNDERSTOOD_TEXT}
        else:
            chosen = candidates[0]

        outcome, task = await task_service.complete(chosen.id, user_id, status)
        if outcome is not Outcome.UPDATED or task is None:
            return {"reply": NOTHING_TO_CLOSE_TEXT}
        return {"reply": render_task_completed(task, cancelled=status is TaskStatus.CANCELLED)}

    return complete_task


def pick_candidate(answer: str, candidates: list[Task]) -> Task | None:
    """Read the owner's choice as a position in the list, or as words again."""
    stripped = answer.strip().rstrip(".")
    if stripped.isdigit():
        index = int(stripped) - 1
        return candidates[index] if 0 <= index < len(candidates) else None
    narrowed = find_matches(stripped, candidates)
    return narrowed[0] if len(narrowed) == 1 else None


async def smalltalk(state: DialogState) -> StateUpdate:
    parsed = state.get("parsed")
    reply = parsed.smalltalk_reply if parsed is not None else None
    return {"reply": (reply or "").strip() or DEFAULT_SMALLTALK_REPLY}


async def unparsed(state: DialogState) -> StateUpdate:
    # The parse node already wrote the reply; this node only terminates the branch.
    return {}


# Node names double as the routing keys returned by route_by_intent.
BRANCH_NODES = [intent.value for intent in Intent] + [UNPARSED_ROUTE]
ROUTES = BRANCH_NODES + [CLARIFY_ROUTE]
