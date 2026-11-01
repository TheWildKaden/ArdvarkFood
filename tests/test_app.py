import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient

import app as app_module
from app import create_app
from local_image_generator import ImageModelUnavailable


class FakeImageGenerator:
    status = "ready"
    device = "cpu"

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int | None]] = []

    def generate(self, prompt: str, steps: int, seed: int | None) -> bytes:
        self.calls.append((prompt, steps, seed))
        return b"\x89PNG\r\n\x1a\nTest image"


def test_homepage_and_health_endpoint() -> None:
    client = TestClient(create_app())

    homepage = client.get("/")
    assert homepage.status_code == 200
    assert "Ardvark" in homepage.text
    assert "ChatGPT, image API, or API key" in homepage.text
    assert client.get("/api/health").json() == {"status": "ok"}


def test_image_generation_runs_the_local_model_and_serves_the_result(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = FakeImageGenerator()
    app_image_directory = tmp_path / "generated"
    monkeypatch.setattr(app_module, "GENERATED_IMAGE_DIR", str(app_image_directory))
    client = TestClient(create_app(image_generator=generator))
    assert client.get("/api/images/status").json() == {
        "model": "SD-Turbo",
        "model_id": "stabilityai/sd-turbo",
        "device": "cpu",
        "status": "ready",
    }

    response = client.post(
        "/api/images/generate",
        json={"prompt": "A red panda in a space suit", "steps": 4, "seed": 123},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["model"] == "SD-Turbo"
    assert result["prompt"] == "A red panda in a space suit"
    assert re.fullmatch(r"/api/images/[a-f0-9]{32}\.png", result["image_url"])
    assert generator.calls == [("A red panda in a space suit", 4, 123)]
    image_response = client.get(result["image_url"])
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"
    assert image_response.content == b"\x89PNG\r\n\x1a\nTest image"


def test_image_generation_is_local_and_needs_no_api_key(monkeypatch) -> None:
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(create_app(image_generator=FakeImageGenerator()))

    response = client.post(
        "/api/images/generate",
        json={"prompt": "A mountain at sunrise"},
    )

    assert response.status_code == 200


def test_image_generation_reports_unavailable_local_model() -> None:
    class UnavailableImageGenerator(FakeImageGenerator):
        def generate(self, prompt: str, steps: int, seed: int | None) -> bytes:
            raise ImageModelUnavailable("Install the local image model dependencies.")

    client = TestClient(create_app(image_generator=UnavailableImageGenerator()))

    response = client.post(
        "/api/images/generate",
        json={"prompt": "A mountain at sunrise"},
    )

    assert response.status_code == 503
    assert "local image model dependencies" in response.json()["detail"]


@pytest.mark.parametrize(
    "payload",
    [
        {"prompt": ""},
        {"prompt": "an image", "steps": 0},
        {"prompt": "an image", "steps": 5},
        {"prompt": "an image", "seed": -1},
    ],
)
def test_image_generation_rejects_invalid_input(payload: dict) -> None:
    response = TestClient(create_app(image_generator=FakeImageGenerator())).post(
        "/api/images/generate",
        json=payload,
    )

    assert response.status_code == 422


def test_generated_image_endpoint_rejects_invalid_filenames() -> None:
    response = TestClient(create_app()).get("/api/images/../../README.md")

    assert response.status_code == 404


def test_chat_calls_provider_with_ardvark_instructions(monkeypatch: pytest.MonkeyPatch) -> None:
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
    assert "You are Ardvark" in payload["messages"][0]["content"]
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
