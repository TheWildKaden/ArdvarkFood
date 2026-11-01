import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class SamplingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.95, gt=0.0, le=1.0)
    top_k: int = Field(default=40, ge=0, le=1000)
    repetition_penalty: float = Field(default=1.1, ge=0.5, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)
    stop: list[str] = Field(default_factory=list, max_length=8)


@dataclass(frozen=True)
class ModelMetadata:
    name: str
    backend: str
    context_size: int
    capabilities: dict[str, bool] = field(default_factory=dict)
    tokenizer: str = "approximate"


@dataclass(frozen=True)
class GenerationResponse:
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None
    usage: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class GenerationDelta:
    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None


class ModelAdapter(Protocol):
    metadata: ModelMetadata

    async def load(self) -> None: ...

    async def unload(self) -> None: ...

    def tokenize(self, text: str) -> list[int]: ...

    async def generate(
        self,
        messages: list[dict[str, Any]],
        sampling: SamplingConfig,
        tools: list[dict[str, Any]],
    ) -> GenerationResponse: ...

    def stream(
        self,
        messages: list[dict[str, Any]],
        sampling: SamplingConfig,
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[GenerationDelta]: ...


class InferenceError(RuntimeError):
    pass


class ModelNotLoaded(InferenceError):
    pass


class ContextWindowExceeded(InferenceError):
    pass


class InferenceEngine:
    def __init__(self, model_manager: Any, context_reserve: int = 128) -> None:
        self.model_manager = model_manager
        self.context_reserve = context_reserve

    def fit_context(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int | None = None,
    ) -> list[dict[str, Any]]:
        adapter = self.model_manager.get_adapter()
        context_size = adapter.metadata.context_size
        output_budget = max_tokens or min(1024, context_size // 4)
        input_budget = context_size - output_budget - self.context_reserve
        if input_budget < 1:
            raise ContextWindowExceeded("The model context window is too small.")

        retained = [dict(message) for message in messages]
        system = retained[:1] if retained and retained[0].get("role") == "system" else []
        conversation = retained[len(system) :]

        while self._count(adapter, system + conversation) > input_budget:
            if len(conversation) <= 1:
                raise ContextWindowExceeded(
                    "The current message exceeds the model's available context window."
                )
            conversation.pop(0)
            if conversation and conversation[0].get("role") == "assistant":
                conversation.pop(0)
        return system + conversation

    async def generate(
        self,
        messages: list[dict[str, Any]],
        sampling: SamplingConfig,
        tools: list[dict[str, Any]] | None = None,
    ) -> GenerationResponse:
        adapter = self.model_manager.get_adapter()
        prepared = self.fit_context(messages, sampling.max_tokens)
        return await adapter.generate(prepared, sampling, tools or [])

    async def stream(
        self,
        messages: list[dict[str, Any]],
        sampling: SamplingConfig,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[GenerationDelta]:
        adapter = self.model_manager.get_adapter()
        prepared = self.fit_context(messages, sampling.max_tokens)
        async for delta in adapter.stream(prepared, sampling, tools or []):
            yield delta

    @staticmethod
    def _count(adapter: ModelAdapter, messages: list[dict[str, Any]]) -> int:
        token_count = 0
        for message in messages:
            token_count += 4
            content = message.get("content", "")
            if isinstance(content, str):
                token_count += len(adapter.tokenize(content))
            else:
                token_count += len(
                    adapter.tokenize(json.dumps(content, ensure_ascii=False))
                )
            for key in ("tool_calls", "tool_call_id", "name"):
                value = message.get(key)
                if value:
                    token_count += len(
                        adapter.tokenize(json.dumps(value, ensure_ascii=False))
                    )
        return token_count + 2