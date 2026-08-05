"""The real LLM client: OpenRouter through the OpenAI-compatible interface."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from openai import APIConnectionError, APIStatusError, AsyncOpenAI, OpenAIError

from graph.llm import LLMError

REQUEST_TIMEOUT_SECONDS = 30.0
MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 1.0


def is_retryable(error: OpenAIError) -> bool:
    """Rate limits, timeouts and a provider in trouble pass; a bad request does not.

    Retrying a 400 or a 401 only burns the owner's time — the same request will
    fail the same way.
    """
    if isinstance(error, APIConnectionError):  # APITimeoutError is a subclass
        return True
    if isinstance(error, APIStatusError):
        return error.status_code == 429 or error.status_code >= 500
    return False


class OpenRouterClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
        max_attempts: int = MAX_ATTEMPTS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            # The backoff below is the retry policy; letting the SDK retry silently
            # underneath it would double the attempts.
            max_retries=0,
        )
        self._model = model
        self._max_attempts = max_attempts
        self._sleep = sleep

    async def complete(self, *, system: str, user: str) -> str:
        last_error: OpenAIError | None = None
        for attempt in range(self._max_attempts):
            try:
                return await self._request(system=system, user=user)
            except OpenAIError as error:
                if not is_retryable(error):
                    raise LLMError(f"OpenRouter request failed: {error}") from error
                last_error = error
                if attempt + 1 < self._max_attempts:
                    await self._sleep(BACKOFF_BASE_SECONDS * 2**attempt)

        raise LLMError(
            f"OpenRouter unavailable after {self._max_attempts} attempts: {last_error}"
        ) from last_error

    async def _request(self, *, system: str, user: str) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            raise LLMError("OpenRouter returned an empty message")
        return content

    async def aclose(self) -> None:
        await self._client.close()
