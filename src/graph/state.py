"""Dialog state carried through the graph."""

from __future__ import annotations

from datetime import datetime
from typing import NotRequired, TypedDict

from graph.schemas import ParsedMessage


class DialogState(TypedDict):
    """Full state. The three input keys are always present."""

    user_id: int
    text: str
    now: datetime
    parsed: NotRequired[ParsedMessage | None]
    reply: NotRequired[str]
    # Set once the owner has been asked a question about this message. Guarantees
    # the second pass cannot ask again.
    clarified: NotRequired[bool]


class StateUpdate(TypedDict, total=False):
    """What a node contributes back. LangGraph merges it into DialogState."""

    parsed: ParsedMessage | None
    reply: str
    clarified: bool
