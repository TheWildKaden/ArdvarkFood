import asyncio
import importlib
from typing import Any

import httpx


settings_module = importlib.import_module("runtime.config.settings")
adapter_module = importlib.import_module(
    "runtime.models.adapters.openai_compatible"
)
inference_module = importlib.import_module("runtime.models.inference")


def test_compatible_backend_invokes_model_and_streams_tokens() -> None:
    async def verify() -> None:
        requests: list[dict[str, Any]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(__import__("json").loads(request.content))
            if requests[-1]["stream"]:
                return httpx.Response(
                    200,
                    text=(
                        'data: {"choices":[{"delta":{"content":"streamed "}}]}\n\n'
                        'data: {"choices":[{"delta":{"content":"output"},"finish_reason":"stop"}]}\n\n'
                        "data: [DONE]\n\n"
                    ),
                    headers={"content-type": "text/event-stream"},
                )
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {"content": "generated"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 2},
                },
            )

        settings = settings_module.ModelSettings(
            backend="openai_compatible",
            base_url="http://model.test/v1",
            model_name="test-model",
        )
        adapter = adapter_module.OpenAICompatibleAdapter(settings)
        adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        sampling = inference_module.SamplingConfig(
            temperature=0.2, top_p=0.8, top_k=10, max_tokens=50
        )
        messages = [{"role": "user", "content": "hello"}]
        response = await adapter.generate(messages, sampling, [])
        assert response.content == "generated"
        assert response.usage["prompt_tokens"] == 12
        assert requests[0]["temperature"] == 0.2
        assert requests[0]["max_tokens"] == 50

        chunks = [
            item.content async for item in adapter.stream(messages, sampling, [])
        ]
        assert "".join(chunks) == "streamed output"
        assert requests[1]["stream"] is True
        await adapter.unload()

    asyncio.run(verify())
