import importlib
import asyncio
import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
settings_module = importlib.import_module("AI-Runtime.config.settings")
inference_module = importlib.import_module("AI-Runtime.models.inference")
model_manager_module = importlib.import_module("AI-Runtime.models.model_manager")
app_module = importlib.import_module("app")


class StreamingAdapter:
    def __init__(self, _settings) -> None:
        self.metadata = inference_module.ModelMetadata(
            name="test-model",
            backend="fake",
            context_size=2048,
            capabilities={"tools": True, "streaming": True, "vision": False},
        )

    async def load(self) -> None:
        return None

    async def unload(self) -> None:
        return None

    def tokenize(self, text: str) -> list[int]:
        return list(range((len(text) + 3) // 4))

    async def generate(self, messages, sampling, tools):
        return inference_module.GenerationResponse(content="unused")

    async def stream(self, messages, sampling, tools):
        yield inference_module.GenerationDelta(content="custom ")
        yield inference_module.GenerationDelta(
            content="stream", finish_reason="stop"
        )


def test_runtime_routes_are_mounted_on_existing_app(tmp_path, monkeypatch) -> None:
    settings = settings_module.RuntimeSettings(
        model=settings_module.ModelSettings(backend="fake", context_size=2048),
        tools=settings_module.ToolSettings(workspace_root=str(ROOT)),
        storage=settings_module.StorageSettings(
            database_path=str(tmp_path / "runtime.sqlite3")
        ),
    )
    monkeypatch.setattr(
        settings_module.RuntimeSettings,
        "load",
        classmethod(lambda cls, path=None: settings),
    )
    monkeypatch.setattr(
        model_manager_module.ModelManager,
        "_make_adapter",
        lambda self, model_settings: StreamingAdapter(model_settings),
    )
    with TestClient(app_module.create_app()) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        status = client.get("/api/runtime/status")
        assert status.status_code == 200
        assert status.json()["model"]["status"] == "unloaded"
        assert client.get("/api/runtime/tools").status_code == 200

        created = client.post(
            "/api/runtime/conversations", json={"title": "runtime integration"}
        )
        assert created.status_code == 200
        conversation_id = created.json()["id"]
        details = client.get(f"/api/runtime/conversations/{conversation_id}")
        assert details.status_code == 200
        assert details.json()["messages"] == []

        chat = client.post(
            "/api/runtime/chat",
            json={"conversation_id": conversation_id, "message": "Hello"},
        )
        assert chat.status_code == 503
        assert client.post("/api/runtime/models/load").status_code == 200
        streamed = client.post(
            "/api/runtime/chat",
            json={
                "conversation_id": conversation_id,
                "message": "Stream this",
                "stream": True,
            },
        )
        assert streamed.status_code == 200
        assert streamed.headers["content-type"].startswith("text/event-stream")
        assert "event: token" in streamed.text
        assert "custom " in streamed.text
        assert "event: final" in streamed.text
        conversations = client.get("/api/runtime/conversations").json()
        assert conversations[0]["id"] == conversation_id
        assert conversations[0]["last_message"] == "custom stream"
