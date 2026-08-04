"""`extract` — the evaluation seam: text plus the current moment in, structure out.

Used by the graph on every message and by the golden set when the real model is
being judged. It knows nothing about the database or Telegram.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from graph.llm import LLMClient
from graph.prompts import build_system_prompt
from graph.schemas import ParsedMessage


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


async def extract(
    llm: LLMClient,
    *,
    text: str,
    now: datetime,
    timezone: ZoneInfo,
) -> ParsedMessage:
    """Raises LLMError on provider failure and ValidationError on unusable output."""
    system = build_system_prompt(now.astimezone(timezone))
    raw = await llm.complete(system=system, user=text)
    parsed = ParsedMessage.model_validate_json(strip_code_fence(raw))
    return normalize_due_at(parsed, timezone)
