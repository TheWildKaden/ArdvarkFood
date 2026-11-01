import os
import re
from typing import Literal
from uuid import uuid4
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from local_image_generator import (
    ImageGenerationError,
    ImageGenerator,
    ImageModelUnavailable,
    LocalImageGenerator,
)


ROOT = os.path.dirname(os.path.abspath(__file__))
MAX_MESSAGE_LENGTH = 8_000
MAX_CONVERSATION_MESSAGES = 32
MAX_IMAGE_PROMPT_LENGTH = 4_000
GENERATED_IMAGE_DIR = os.path.join(ROOT, ".generated")


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(
        min_length=1, max_length=MAX_CONVERSATION_MESSAGES
    )

    @model_validator(mode="after")
    def validate_conversation(self) -> "ChatRequest":
        for index, message in enumerate(self.messages):
            expected_role = "user" if index % 2 == 0 else "assistant"
            if message.role != expected_role:
                raise ValueError("Messages must alternate between user and assistant.")
        if self.messages[-1].role != "user":
            raise ValueError("The conversation must end with a user message.")
        return self


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_IMAGE_PROMPT_LENGTH)
    steps: int = Field(default=1, ge=1, le=4)
    seed: int | None = Field(default=None, ge=0, le=4_294_967_295)


def create_app(
    *,
    ai_transport: httpx.AsyncBaseTransport | None = None,
    image_generator: ImageGenerator | None = None,
) -> FastAPI:
    application = FastAPI(title="AI Buddy")
    local_generator = image_generator or LocalImageGenerator()

    @application.get("/", include_in_schema=False)
    async def home() -> FileResponse:
        return FileResponse(os.path.join(ROOT, "static", "index.html"))

    @application.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/api/chat")
    async def chat(request: ChatRequest) -> dict[str, str]:
        api_key = os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail=(
                    "AI Buddy needs an API key. Add AI_API_KEY as a Codespaces "
                    "secret (or set OPENAI_API_KEY), then restart the app."
                ),
            )

        base_url = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        parsed_url = urlsplit(base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise HTTPException(
                status_code=500,
                detail="AI_BASE_URL must be a valid HTTP or HTTPS URL.",
            )

        model = os.getenv("AI_MODEL", "gpt-5.5")
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": os.getenv(
                        "AI_SYSTEM_PROMPT",
                        "You are Buddy, a friendly, capable general-purpose AI "
                        "assistant. Give clear, useful answers. Be honest about "
                        "uncertainty, and never claim to have taken actions you "
                        "have not taken.",
                    ),
                },
                *[message.model_dump() for message in request.messages],
            ],
            "max_completion_tokens": 1_000,
        }

        try:
            async with httpx.AsyncClient(
                transport=ai_transport,
                timeout=httpx.Timeout(60.0, connect=10.0),
            ) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                )
                response.raise_for_status()
        except httpx.TimeoutException as error:
            raise HTTPException(
                status_code=504,
                detail="The AI provider took too long to respond. Try again.",
            ) from error
        except httpx.HTTPStatusError as error:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"The AI provider returned HTTP "
                    f"{error.response.status_code}. Check your API key, model, "
                    "and provider settings."
                ),
            ) from error
        except httpx.RequestError as error:
            raise HTTPException(
                status_code=502,
                detail="Could not reach the AI provider. Check its URL and try again.",
            ) from error

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise HTTPException(
                status_code=502,
                detail="The AI provider returned an invalid chat response.",
            ) from error
        if not isinstance(content, str) or not content.strip():
            raise HTTPException(
                status_code=502,
                detail="The AI provider returned an empty chat response.",
            )

        return {"reply": content, "model": model}

    @application.get("/api/images/status")
    async def image_status() -> dict[str, str]:
        return {
            "model": "SD-Turbo",
            "model_id": "stabilityai/sd-turbo",
            "device": local_generator.device,
            "status": local_generator.status,
        }

    @application.post("/api/images/generate")
    async def generate_image(request: ImageGenerationRequest) -> dict[str, str]:
        try:
            image_bytes = await run_in_threadpool(
                local_generator.generate,
                request.prompt,
                request.steps,
                request.seed,
            )
        except ImageModelUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except ImageGenerationError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(
                status_code=502,
                detail="The local image model did not return a valid PNG image.",
            )

        filename = f"{uuid4().hex}.png"
        os.makedirs(GENERATED_IMAGE_DIR, exist_ok=True)
        with open(os.path.join(GENERATED_IMAGE_DIR, filename), "wb") as image_file:
            image_file.write(image_bytes)
        return {
            "image_url": f"/api/images/{filename}",
            "model": "SD-Turbo",
            "prompt": request.prompt,
        }

    @application.get("/api/images/{filename}", include_in_schema=False)
    async def get_generated_image(filename: str) -> FileResponse:
        if not re.fullmatch(r"[a-f0-9]{32}\.png", filename):
            raise HTTPException(status_code=404, detail="Image not found.")
        image_path = os.path.join(GENERATED_IMAGE_DIR, filename)
        if not os.path.isfile(image_path):
            raise HTTPException(status_code=404, detail="Image not found.")
        return FileResponse(image_path, media_type="image/png")

    return application


app = create_app()
