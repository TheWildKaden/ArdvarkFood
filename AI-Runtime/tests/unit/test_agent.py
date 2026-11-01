import asyncio
import importlib
import sys
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
settings_module = importlib.import_module("AI-Runtime.config.settings")
agent_module = importlib.import_module("AI-Runtime.agent.agent")
inference_module = importlib.import_module("AI-Runtime.models.inference")


class FakeAdapter:
    def __init__(self, _settings: Any) -> None:
        self.metadata = inference_module.ModelMetadata(
            name="test-model",
            backend="fake",
            context_size=2048,
            capabilities={"tools": True, "streaming": True, "vision": False},
        )
        self.responses = [
            inference_module.GenerationResponse(
                content="",
                tool_calls=[
                    {
                        "id": "read-a",
                        "type": "function",
                        "function": {
                            "name": "filesystem.read",
                            "arguments": '{"path":"a.txt"}',
                        },
                    },
                    {
                        "id": "read-b",
                        "type": "function",
                        "function": {
                            "name": "filesystem.read",
                            "arguments": '{"path":"b.txt"}',
                        },
                    },
                ],
            ),
            inference_module.GenerationResponse(content="Both files are available."),
        ]

    async def load(self) -> None:
        return None

    async def unload(self) -> None:
        return None

    def tokenize(self, text: str) -> list[int]:
        return list(text.encode("utf-8"))

    async def generate(self, messages, sampling, tools):
        return self.responses.pop(0)

    async def stream(self, messages, sampling, tools):
        response = self.responses.pop(0)
        if response.content:
            for chunk in ("Both ", "files are available."):
                yield inference_module.GenerationDelta(content=chunk)
        else:
            yield inference_module.GenerationDelta(
                tool_calls=[
                    {"index": index, **call}
                    for index, call in enumerate(response.tool_calls)
                ]
            )
            yield inference_module.GenerationDelta(finish_reason="tool_calls")


def _settings(tmp_path: Path):
    return settings_module.RuntimeSettings(
        model=settings_module.ModelSettings(backend="fake", context_size=2048),
        tools=settings_module.ToolSettings(workspace_root=str(tmp_path)),
        storage=settings_module.StorageSettings(
            database_path=str(tmp_path / "runtime.sqlite3")
        ),
    )


def test_agent_executes_multiple_tools_then_finishes_with_streamed_response(
    tmp_path: Path,
) -> None:
    async def verify() -> None:
        settings = _settings(tmp_path)
        (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
        (tmp_path / "b.txt").write_text("beta", encoding="utf-8")
        manager = importlib.import_module(
            "AI-Runtime.models.model_manager"
        ).ModelManager(settings.model, {"fake": FakeAdapter})
        await manager.load()
        runtime = agent_module.AgentRuntime(settings, model_manager=manager)
        conversation_id = runtime.storage.create_conversation("test")["id"]
        handle = await runtime.start(
            conversation_id,
            "Read both files.",
            stream_tokens=True,
        )
        events = []
        while True:
            event = await asyncio.wait_for(handle.events.get(), timeout=2)
            events.append(event)
            if event["event"] == "end":
                break

        assert await handle.task == "Both files are available."
        assert handle.state.tool_calls == 2
        assert runtime.storage.get_execution(handle.state.execution_id)["status"] == "completed"
        assert [item["content"] for item in runtime.storage.get_messages(conversation_id)] == [
            "Read both files.",
            "Both files are available.",
        ]
        assert "".join(
            item["data"]["content"] for item in events if item["event"] == "token"
        ) == "Both files are available."
        assert sum(item["event"] == "tool_result" for item in events) == 2
        await runtime.close()

    asyncio.run(verify())


def test_context_window_rejects_single_oversized_message(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    manager = importlib.import_module(
        "AI-Runtime.models.model_manager"
    ).ModelManager(settings.model, {"fake": FakeAdapter})
    asyncio.run(manager.load())
    engine = inference_module.InferenceEngine(manager, context_reserve=128)
    try:
        engine.fit_context(
            [{"role": "user", "content": "x" * 10000}],
            max_tokens=512,
        )
    except inference_module.ContextWindowExceeded:
        pass
    else:
        raise AssertionError("Expected an oversized message to exceed context.")
    asyncio.run(manager.unload())