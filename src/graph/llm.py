"""The LLM seam. The real OpenRouter client arrives in ticket 04."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from typing import Protocol


class LLMError(Exception):
    """The provider was unreachable, rate limited or otherwise unusable."""


class LLMClient(Protocol):
    async def complete(self, *, system: str, user: str) -> str:
        """Return the raw model response. Raises LLMError on provider failure."""
        ...


class ScriptedLLMClient:
    """Replays canned raw responses in order. Stands in for the provider."""

    def __init__(self, responses: Iterable[str] = (), *, default: str | None = None) -> None:
        self._responses: deque[str] = deque(responses)
        self._default = default
        self.calls: list[tuple[str, str]] = []

    async def complete(self, *, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self._responses:
            return self._responses.popleft()
        if self._default is not None:
            return self._default
        raise LLMError("ScriptedLLMClient ran out of scripted responses")
