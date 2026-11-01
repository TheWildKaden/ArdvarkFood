import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
settings_module = importlib.import_module("AI-Runtime.config.settings")
app_module = importlib.import_module("app")


def test_runtime_routes_are_mounted_on_existing_app(tmp_path, monkeypatch) -> None:
    settings = settings_module.RuntimeSettings(
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
        conversations = client.get("/api/runtime/conversations").json()
        assert conversations[0]["id"] == conversation_id
        assert conversations[0]["last_message"] == "Hello"
