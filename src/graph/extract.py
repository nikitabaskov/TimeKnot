"""`extract` — the evaluation seam: text plus the current moment in, structure out.

Used by the graph on every message and by the golden set when the real model is
being judged. It knows nothing about the database or Telegram.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from graph.llm import LLMClient
from graph.prompts import build_clarification_prompt, build_retry_note, build_system_prompt
from graph.schemas import ParsedMessage

MAX_HORIZON = timedelta(days=365)


class DueDateRejected(Exception):
    """A moment the code refuses to store: already gone, or absurdly far ahead."""

    def __init__(self, *, past: bool) -> None:
        super().__init__("due date in the past" if past else "due date beyond the horizon")
        self.past = past


def strip_code_fence(raw: str) -> str:
    """Models wrap JSON in ``` fences often enough that not handling it is a bug."""
    text = raw.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines[-1].strip() == "```":
        lines = lines[:-1]
    # The opening fence may carry a language tag, as in ```json.
    return "\n".join(lines[1:]).strip()


def normalize_due_at(parsed: ParsedMessage, timezone: ZoneInfo) -> ParsedMessage:
    """Make `due_at` an aware UTC moment.

    The prompt asks for an offset, but models drop it regularly. A naive answer
    means local time — that is what the user was talking about.
    """
    if parsed.due_at is None:
        return parsed
    due_at = parsed.due_at
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=timezone)
    parsed.due_at = due_at.astimezone(UTC)
    return parsed


def ensure_due_at_is_usable(parsed: ParsedMessage, now: datetime) -> None:
    """Schema validation only proves `due_at` is a date; this proves it is a deadline.

    A moment that has already passed would be stored as a task nobody is ever
    reminded of, and one a year out is a model slip, not an intention.
    """
    if parsed.due_at is None:
        return
    if parsed.due_at <= now:
        raise DueDateRejected(past=True)
    if parsed.due_at - now > MAX_HORIZON:
        raise DueDateRejected(past=False)


async def extract(
    llm: LLMClient,
    *,
    text: str,
    now: datetime,
    timezone: ZoneInfo,
) -> ParsedMessage:
    """Raises LLMError on provider failure and ValidationError on unusable output."""
    system = build_system_prompt(now.astimezone(timezone))
    return await _complete_and_parse(llm, system=system, user=text, now=now, timezone=timezone)


async def extract_after_clarification(
    llm: LLMClient,
    *,
    original: str,
    question: str,
    answer: str,
    now: datetime,
    timezone: ZoneInfo,
) -> ParsedMessage:
    """Re-read the exchange once the owner has answered the question."""
    system = build_clarification_prompt(
        now.astimezone(timezone), original=original, question=question, answer=answer
    )
    parsed = await _complete_and_parse(llm, system=system, user=answer, now=now, timezone=timezone)
    # One question per task: whatever the model says now, it does not get to ask again.
    parsed.needs_clarification = False
    parsed.clarification_question = None
    return parsed


async def _complete_and_parse(
    llm: LLMClient, *, system: str, user: str, now: datetime, timezone: ZoneInfo
) -> ParsedMessage:
    try:
        parsed = await _parse_once(llm, system=system, user=user, timezone=timezone)
    except ValidationError as error:
        # Exactly one retry, with the validator's own complaint handed back to the
        # model. A second failure is the caller's to report — this is not a loop.
        parsed = await _parse_once(
            llm, system=system + build_retry_note(error), user=user, timezone=timezone
        )

    # Deliberately outside the retry: a date in the past is a well-formed answer
    # to the wrong question, and the owner is told rather than the model re-asked.
    ensure_due_at_is_usable(parsed, now)
    return parsed


async def _parse_once(
    llm: LLMClient, *, system: str, user: str, timezone: ZoneInfo
) -> ParsedMessage:
    raw = await llm.complete(system=system, user=user)
    parsed = ParsedMessage.model_validate_json(strip_code_fence(raw))
    return normalize_due_at(parsed, timezone)
