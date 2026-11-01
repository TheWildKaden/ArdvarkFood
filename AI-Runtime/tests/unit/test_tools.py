import asyncio
import importlib
import sys
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
settings_module = importlib.import_module("AI-Runtime.config.settings")
agent_module = importlib.import_module("AI-Runtime.agent.agent")
inference_module = importlib.import_module("AI-Runtime.models.inference")
tool_call_module = importlib.import_module("AI-Runtime.tools.tool_call")


def _settings(tmp_path: Path):
    return settings_module.RuntimeSettings(
        model=settings_module.ModelSettings(backend="fake"),
        tools=settings_module.ToolSettings(workspace_root=str(tmp_path)),
        storage=settings_module.StorageSettings(
            database_path=str(tmp_path / "runtime.sqlite3")
        ),
    )


def test_tool_registry_discovery_and_validation(tmp_path: Path) -> None:
    async def verify() -> None:
        runtime = agent_module.AgentRuntime(_settings(tmp_path))
        names = {tool.name for tool in runtime.tool_registry.discover()}
        assert {"filesystem.read", "filesystem.write", "terminal.execute"} <= names
        readme = tmp_path / "note.txt"
        readme.write_text("safe content", encoding="utf-8")
        conversation_id = runtime.storage.create_conversation()["id"]
        execution_id = runtime.storage.start_execution(conversation_id)
        events: list[tuple[str, dict[str, Any]]] = []

        async def notify(event: str, data: dict[str, Any]) -> None:
            events.append((event, data))

        valid = await runtime.tool_executor.execute(
            execution_id,
            {
                "id": "read-1",
                "function": {
                    "name": "filesystem.read",
                    "arguments": '{"path":"note.txt"}',
                },
            },
            notify,
        )
        assert valid.status == "ok"
        assert valid.content["content"] == "safe content"

        invalid = await runtime.tool_executor.execute(
            execution_id,
            {
                "id": "read-2",
                "function": {
                    "name": "filesystem.read",
                    "arguments": '{"path":"../../etc/passwd"}',
                },
            },
            notify,
        )
        assert invalid.status == "error"
        assert "workspace" in invalid.error

        malformed = await runtime.tool_executor.execute(
            execution_id,
            {
                "id": "read-3",
                "function": {
                    "name": "filesystem.read",
                    "arguments": '{"unexpected":true}',
                },
            },
            notify,
        )
        assert malformed.status == "error"
        await runtime.close()

    asyncio.run(verify())


def test_permission_is_required_and_can_be_denied(tmp_path: Path) -> None:
    async def verify() -> None:
        runtime = agent_module.AgentRuntime(_settings(tmp_path))
        conversation_id = runtime.storage.create_conversation()["id"]
        execution_id = runtime.storage.start_execution(conversation_id)
        approval_requested = asyncio.Event()
        call_id = "terminal-1"

        async def notify(event: str, data: dict[str, Any]) -> None:
            if event == "approval_required":
                assert data["tool_call_id"] == call_id
                approval_requested.set()

        task = asyncio.create_task(
            runtime.tool_executor.execute(
                execution_id,
                {
                    "id": call_id,
                    "function": {
                        "name": "terminal.execute",
                        "arguments": '{"command":["pwd"]}',
                    },
                },
                notify,
            )
        )
        await asyncio.wait_for(approval_requested.wait(), timeout=1)
        assert runtime.approve(execution_id, call_id, False)
        result = await task
        assert result.status == "error"
        assert "denied" in result.error
        await runtime.close()

    asyncio.run(verify())


def test_tool_call_parser_rejects_non_object_arguments() -> None:
    try:
        tool_call_module.ToolCall.from_model(
            {"id": "bad", "function": {"name": "example", "arguments": "[]"}}
        )
    except tool_call_module.InvalidToolCall:
        return
    raise AssertionError("Expected malformed tool arguments to be rejected.")