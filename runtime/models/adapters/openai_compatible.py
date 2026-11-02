import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ...config.settings import ModelSettings
from ..inference import (
    GenerationDelta,
    GenerationResponse,
    ModelMetadata,
    SamplingConfig,
)
from ..tokenizers.tokenizer import ApproximateTokenizer


class OpenAICompatibleAdapter:
    """Adapter for explicitly configured OpenAI-compatible local model servers."""

    def __init__(self, settings: ModelSettings) -> None:
        self.settings = settings
        self._tokenizer = ApproximateTokenizer()
        self._client: httpx.AsyncClient | None = None
        self.metadata = ModelMetadata(
            name=settings.model_name,
            backend="openai_compatible",
            context_size=settings.context_size,
            capabilities={
                "tools": True,
                "streaming": True,
                "vision": False,
                "audio": False,
                "video": False,
            },
        )

    async def load(self) -> None:
        if not self.settings.base_url:
            raise ValueError(
                "Set AI_RUNTIME_BASE_URL to the configured model server's /v1 endpoint."
            )
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=10.0),
            trust_env=False,
        )

    async def unload(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def tokenize(self, text: str) -> list[int]:
        return self._tokenizer.encode(text)

    async def generate(
        self,
        messages: list[dict[str, Any]],
        sampling: SamplingConfig,
        tools: list[dict[str, Any]],
    ) -> GenerationResponse:
        response = await self._request(messages, sampling, tools, stream=False)
        choice = response["choices"][0]
        message = choice["message"]
        return GenerationResponse(
            content=message.get("content") or "",
            tool_calls=message.get("tool_calls") or [],
            finish_reason=choice.get("finish_reason"),
            usage={
                key: value
                for key, value in (response.get("usage") or {}).items()
                if isinstance(value, int)
            },
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        sampling: SamplingConfig,
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[GenerationDelta]:
        client = self._require_client()
        async with client.stream(
            "POST",
            self._url(),
            headers=self._headers(),
            json=self._payload(messages, sampling, tools, stream=True),
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    choice = chunk["choices"][0]
                    delta = choice.get("delta") or {}
                except (ValueError, KeyError, IndexError, TypeError) as error:
                    raise RuntimeError(
                        "The model server returned an invalid streaming response."
                    ) from error
                yield GenerationDelta(
                    content=delta.get("content") or "",
                    tool_calls=delta.get("tool_calls") or [],
                    finish_reason=choice.get("finish_reason"),
                )

    async def _request(
        self,
        messages: list[dict[str, Any]],
        sampling: SamplingConfig,
        tools: list[dict[str, Any]],
        stream: bool,
    ) -> dict[str, Any]:
        client = self._require_client()
        response = await client.post(
            self._url(),
            headers=self._headers(),
            json=self._payload(messages, sampling, tools, stream),
        )
        response.raise_for_status()
        return response.json()

    def _payload(
        self,
        messages: list[dict[str, Any]],
        sampling: SamplingConfig,
        tools: list[dict[str, Any]],
        stream: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.settings.model_name,
            "messages": messages,
            "temperature": sampling.temperature,
            "top_p": sampling.top_p,
            "max_tokens": sampling.max_tokens or self.settings.default_max_tokens,
            "stream": stream,
        }
        if sampling.top_k:
            payload["top_k"] = sampling.top_k
        if sampling.repetition_penalty != 1.0:
            payload["repetition_penalty"] = sampling.repetition_penalty
        if sampling.stop:
            payload["stop"] = sampling.stop
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        return payload

    def _url(self) -> str:
        return self.settings.base_url.rstrip("/") + "/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"
        return headers

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("The compatible model adapter has not been loaded.")
        return self._client
