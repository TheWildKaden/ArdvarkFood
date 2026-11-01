import os
from typing import Literal
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator


ROOT = os.path.dirname(os.path.abspath(__file__))
MAX_MESSAGE_LENGTH = 8_000
MAX_CONVERSATION_MESSAGES = 32
MAX_IMAGE_PROMPT_LENGTH = 4_000
MAX_IMAGE_BASE64_LENGTH = 32_000_000


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
    model: Literal["gpt-image-2.5-flare", "gpt-image-2.5-sunburst"] = (
        "gpt-image-2.5-flare"
    )
    size: Literal["1024x1024", "1536x1024", "1024x1536"] = "1024x1024"
    quality: Literal["low", "medium", "high", "auto"] = "medium"


def create_app(
    *,
    ai_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    application = FastAPI(title="AI Buddy")

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

    @application.post("/api/images/generate")
    async def generate_image(request: ImageGenerationRequest) -> dict[str, str]:
        api_key = (
            os.getenv("IMAGE_API_KEY")
            or os.getenv("AI_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Image generation needs an API key. Add IMAGE_API_KEY or "
                    "AI_API_KEY as a Codespaces secret, then restart the app."
                ),
            )

        base_url = os.getenv(
            "IMAGE_BASE_URL", "https://api.openai.com/v1"
        ).rstrip("/")
        parsed_url = urlsplit(base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise HTTPException(
                status_code=500,
                detail="IMAGE_BASE_URL must be a valid HTTP or HTTPS URL.",
            )

        try:
            async with httpx.AsyncClient(
                transport=ai_transport,
                timeout=httpx.Timeout(180.0, connect=10.0),
            ) as client:
                response = await client.post(
                    f"{base_url}/images/generations",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": request.model,
                        "prompt": request.prompt,
                        "size": request.size,
                        "quality": request.quality,
                        "output_format": "png",
                        "n": 1,
                    },
                )
                response.raise_for_status()
        except httpx.TimeoutException as error:
            raise HTTPException(
                status_code=504,
                detail="Image generation took too long. Try again.",
            ) from error
        except httpx.HTTPStatusError as error:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"The image provider returned HTTP "
                    f"{error.response.status_code}. Check your API key, model, "
                    "and provider settings."
                ),
            ) from error
        except httpx.RequestError as error:
            raise HTTPException(
                status_code=502,
                detail="Could not reach the image provider. Check its URL and try again.",
            ) from error

        try:
            image_base64 = response.json()["data"][0]["b64_json"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise HTTPException(
                status_code=502,
                detail="The image provider returned an invalid image response.",
            ) from error
        if not isinstance(image_base64, str) or not image_base64:
            raise HTTPException(
                status_code=502,
                detail="The image provider returned an empty image.",
            )
        if len(image_base64) > MAX_IMAGE_BASE64_LENGTH:
            raise HTTPException(
                status_code=502,
                detail="The generated image exceeded the maximum supported size.",
            )

        import base64
        import binascii

        try:
            image_bytes = base64.b64decode(image_base64, validate=True)
        except (binascii.Error, ValueError) as error:
            raise HTTPException(
                status_code=502,
                detail="The image provider returned invalid image data.",
            ) from error
        if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(
                status_code=502,
                detail="The image provider did not return a valid PNG image.",
            )

        return {
            "image": f"data:image/png;base64,{image_base64}",
            "model": request.model,
            "prompt": request.prompt,
        }

    return application


app = create_app()
