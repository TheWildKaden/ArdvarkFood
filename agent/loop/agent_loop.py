import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from agent.context.context_builder import ContextBuilder
from agent.state.state import AgentState
from runtime.config.settings import RuntimeSettings
from runtime.models.inference import (
    GenerationDelta,
    GenerationResponse,
    InferenceEngine,
    SamplingConfig,
)
from runtime.storage.storage_manager import StorageManager
from runtime.tools.executor.executor import ToolExecutor
from runtime.learning.manager import ConversationLearningManager


logger = logging.getLogger(__name__)
Notify = Callable[[str, dict[str, Any]], Awaitable[None]]


class AgentLoop:
    def __init__(
        self,
        settings: RuntimeSettings,
        inference: InferenceEngine,
        tools: ToolExecutor,
        context: ContextBuilder,
        storage: StorageManager,
        learning: ConversationLearningManager,
    ) -> None:
        self.settings = settings
        self.inference = inference
        self.tools = tools
        self.context = context
        self.storage = storage
        self.learning = learning

    async def run(
        self,
        state: AgentState,
        user_input: str,
        attachments: list[dict[str, Any]],
        notify: Notify,
        sampling: SamplingConfig,
        stream_tokens: bool = False,
    ) -> str:
        self.storage.add_message(
            state.conversation_id,
            "user",
            user_input,
            {"attachments": attachments} if attachments else None,
        )
        command_response = self.learning.handle_command(
            state.conversation_id, user_input
        )
        if command_response is not None:
            state.final_response = command_response
            state.status = "completed"
            self.storage.add_message(
                state.conversation_id, "assistant", command_response
            )
            self.storage.update_execution(
                state.execution_id, "completed", state.snapshot()
            )
            await notify(
                "final",
                {"execution_id": state.execution_id, "content": command_response},
            )
            return command_response
        messages = self.context.build(state.conversation_id, user_input)
        adapter = self.inference.model_manager.get_adapter()
        if attachments and not adapter.metadata.capabilities.get("vision", False):
            image_count = sum(
                item["mime_type"].startswith("image/") for item in attachments
            )
            if image_count:
                raise ValueError(
                    "The loaded model does not support image input. Configure a "
                    "multimodal GGUF model and its CLIP projector."
                )

        for step in range(1, self.settings.agent.max_steps + 1):
            state.step = step
            await notify("status", state.snapshot())
            self.storage.update_execution(state.execution_id, "running", state.snapshot())
            response = await self._generate(
                messages, sampling, notify, stream_tokens
            )
            if not response.tool_calls:
                final = response.content.strip()
                if not final:
                    raise RuntimeError("The model completed without a response.")
                state.final_response = final
                state.status = "completed"
                self.storage.add_message(state.conversation_id, "assistant", final)
                self.storage.update_execution(
                    state.execution_id, "completed", state.snapshot()
                )
                self.learning.queue_memory(state.conversation_id)
                await notify("final", {"execution_id": state.execution_id, "content": final})
                return final

            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": response.content or None,
                "tool_calls": response.tool_calls,
            }
            messages.append(assistant_message)
            for payload in response.tool_calls:
                if state.cancelled:
                    raise asyncio.CancelledError
                if state.tool_calls >= self.settings.agent.max_tool_calls_per_turn:
                    from ...tools.tool_result import ToolResult

                    try:
                        call_id = payload.get("id", "limit")
                        function = payload.get("function", {})
                        tool_name = function.get("name", "unknown")
                        message = ToolResult(
                            call_id=call_id,
                            name=tool_name,
                            status="error",
                            content=None,
                            error="Tool-call limit reached for this turn.",
                        ).to_message()
                    except (AttributeError, TypeError):
                        message = {
                            "role": "tool",
                            "tool_call_id": "limit",
                            "name": "unknown",
                            "content": '{"status":"error","error":"Tool-call limit reached."}',
                        }
                else:
                    state.tool_calls += 1
                    result = await self.tools.execute(state.execution_id, payload, notify)
                    message = result.to_message()
                    await notify("tool_result", result.to_dict())
                messages.append(message)
                self.storage.update_execution(
                    state.execution_id, "running", state.snapshot()
                )

        raise TimeoutError(
            f"The agent reached its {self.settings.agent.max_steps}-step limit."
        )

    async def _generate(
        self,
        messages: list[dict[str, Any]],
        sampling: SamplingConfig,
        notify: Notify,
        stream_tokens: bool,
    ) -> GenerationResponse:
        if not stream_tokens:
            return await self.inference.generate(
                messages, sampling, self.tools.registry.model_schemas()
            )

        stream = self.inference.stream(
            messages, sampling, self.tools.registry.model_schemas()
        )
        chunks: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        finish_reason = None
        async for delta in stream:
            if delta.content:
                chunks.append(delta.content)
                await notify("token", {"content": delta.content})
            if delta.finish_reason:
                finish_reason = delta.finish_reason
            if not isinstance(delta.tool_calls, list):
                raise RuntimeError("The model returned malformed streaming tool calls.")
            for position, fragment in enumerate(delta.tool_calls):
                if not isinstance(fragment, dict):
                    raise RuntimeError("The model returned a malformed streaming tool call.")
                index = fragment.get("index", position)
                if not isinstance(index, int) or index < 0:
                    continue
                call = calls.setdefault(
                    index,
                    {
                        "id": "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    },
                )
                if isinstance(fragment.get("id"), str):
                    call["id"] = fragment["id"]
                function = fragment.get("function") or {}
                if not isinstance(function, dict):
                    raise RuntimeError("The model returned a malformed tool function.")
                if isinstance(function.get("name"), str):
                    call["function"]["name"] += function["name"]
                if isinstance(function.get("arguments"), str):
                    call["function"]["arguments"] += function["arguments"]
        return GenerationResponse(
            content="".join(chunks),
            tool_calls=[calls[index] for index in sorted(calls)],
            finish_reason=finish_reason,
        )