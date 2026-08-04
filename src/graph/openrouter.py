"""The real LLM client: OpenRouter through the OpenAI-compatible interface."""

from __future__ import annotations

from openai import AsyncOpenAI, OpenAIError

from graph.llm import LLMError

REQUEST_TIMEOUT_SECONDS = 30.0


class OpenRouterClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            # Backoff belongs to ticket 10, which owns the retry policy; letting the
            # SDK retry silently underneath it would double the attempts.
            max_retries=0,
        )
        self._model = model

    async def complete(self, *, system: str, user: str) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
        except OpenAIError as error:
            raise LLMError(f"OpenRouter request failed: {error}") from error

        content = response.choices[0].message.content
        if not content:
            raise LLMError("OpenRouter returned an empty message")
        return content

    async def aclose(self) -> None:
        await self._client.close()
