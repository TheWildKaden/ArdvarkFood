import asyncio
import hashlib
import importlib
import sys
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
settings_module = importlib.import_module("AI-Runtime.config.settings")
agent_module = importlib.import_module("AI-Runtime.agent.agent")
inference_module = importlib.import_module("AI-Runtime.models.inference")
tool_call_module = importlib.import_module("AI-Runtime.tools.tool_call")
input_router_module = importlib.import_module("AI-Runtime.multimodal.input_router")


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


def test_workspace_write_requires_current_digest_for_replacements(
    tmp_path: Path,
) -> None:
    runtime = agent_module.AgentRuntime(_settings(tmp_path))
    target = tmp_path / "module.py"
    original = "value = 1\n"
    target.write_text(original, encoding="utf-8")

    try:
        read_result = runtime.tool_executor._read_file("module.py")
        assert read_result["sha256"] == hashlib.sha256(
            original.encode("utf-8")
        ).hexdigest()

        try:
            runtime.tool_executor._write_file("module.py", "value = 2\n")
        except PermissionError as error:
            assert "SHA-256" in str(error)
        else:
            raise AssertionError("Replacing a file without a digest must be rejected.")

        stale_digest = hashlib.sha256(b"value = 0\n").hexdigest()
        try:
            runtime.tool_executor._write_file(
                "module.py", "value = 2\n", stale_digest
            )
        except PermissionError as error:
            assert "changed since it was read" in str(error)
        else:
            raise AssertionError("Replacing a changed file must be rejected.")
        assert target.read_text(encoding="utf-8") == original

        current_digest = hashlib.sha256(original.encode("utf-8")).hexdigest()
        result = runtime.tool_executor._write_file(
            "module.py", "value = 2\n", current_digest
        )
        assert result["created"] is False
        assert result["sha256"] == hashlib.sha256(b"value = 2\n").hexdigest()
        assert target.read_text(encoding="utf-8") == "value = 2\n"

        created = runtime.tool_executor._write_file("new.py", "value = 3\n")
        assert created["created"] is True
        assert (tmp_path / "new.py").read_text(encoding="utf-8") == "value = 3\n"
    finally:
        asyncio.run(runtime.close())


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


def test_multimodal_router_rejects_unsupported_and_mismatched_images() -> None:
    router = input_router_module.InputRouter()
    try:
        router.process(
            [{"name": "clip.gif", "mime_type": "image/gif", "content": "R0lG"}]
        )
    except input_router_module.UnsupportedModality:
        pass
    else:
        raise AssertionError("GIF input should be rejected as unsupported.")

    import base64

    encoded = base64.b64encode(b"not a png").decode("ascii")
    try:
        router.process(
            [{"name": "image.png", "mime_type": "image/png", "content": encoded}]
        )
    except ValueError as error:
        assert "does not match" in str(error)
    else:
        raise AssertionError("Mismatched image data should be rejected.")


def test_running_executions_are_recovered_as_interrupted(tmp_path: Path) -> None:
    storage_module = importlib.import_module("AI-Runtime.storage.storage_manager")
    database_path = str(tmp_path / "recovery.sqlite3")
    first = storage_module.StorageManager(database_path)
    conversation_id = first.create_conversation()["id"]
    execution_id = first.start_execution(conversation_id)

    recovered = storage_module.StorageManager(database_path)
    execution = recovered.get_execution(execution_id)
    assert execution["status"] == "interrupted"
    assert execution["error"] == "Process restarted during execution"