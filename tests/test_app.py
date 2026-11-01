import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import create_app


def test_homepage_and_health_endpoint() -> None:
    client = TestClient(create_app())

    homepage = client.get("/")
    assert homepage.status_code == 200
    assert "AI Buddy" in homepage.text
    assert client.get("/api/health").json() == {"status": "ok"}


def test_chat_calls_provider_with_buddy_instructions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_MODEL", "test-model")
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Hello from the model."}}]},
        )

    client = TestClient(
        create_app(ai_transport=httpx.MockTransport(respond))
    )
    response = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )

    assert response.status_code == 200
    assert response.json() == {"reply": "Hello from the model.", "model": "test-model"}
    assert len(requests) == 1
    assert requests[0].url == "https://api.openai.com/v1/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer test-key"
    payload = json.loads(requests[0].content)
    assert payload["messages"][0]["role"] == "system"
    assert "You are Buddy" in payload["messages"][0]["content"]
    assert payload["messages"][-1] == {"role": "user", "content": "Hello"}


def test_chat_requires_a_real_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(create_app())

    response = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )

    assert response.status_code == 503
    assert "AI_API_KEY" in response.json()["detail"]


def test_chat_rejects_non_alternating_messages() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/chat",
        json={
            "messages": [
                {"role": "user", "content": "First"},
                {"role": "user", "content": "Second"},
            ]
        },
    )

    assert response.status_code == 422


def test_chat_reports_provider_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_API_KEY", "test-key")
    transport = httpx.MockTransport(
        lambda request: httpx.Response(401, json={"error": "unauthorized"})
    )
    client = TestClient(create_app(ai_transport=transport))

    response = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )

    assert response.status_code == 502
    assert "HTTP 401" in response.json()["detail"]
