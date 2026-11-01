import os
import re
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from src.image_generation import (
    ImageGenerationError,
    ImageGenerator,
    ImageModelUnavailable,
)
from .chat_service import generate_chat_response
from .schemas import ChatRequest, ImageGenerationRequest


def create_api_router(
    *,
    ai_transport: httpx.AsyncBaseTransport | None,
    image_generator: ImageGenerator,
    generated_image_dir: str,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.post("/api/chat")
    async def chat(request: ChatRequest) -> dict[str, str]:
        return await generate_chat_response(request, ai_transport)

    @router.get("/api/images/status")
    async def image_status() -> dict[str, str]:
        return {
            "model": "SD-Turbo",
            "model_id": "stabilityai/sd-turbo",
            "device": image_generator.device,
            "status": image_generator.status,
        }

    @router.post("/api/images/generate")
    async def generate_image(request: ImageGenerationRequest) -> dict[str, str]:
        try:
            image_bytes = await run_in_threadpool(
                image_generator.generate,
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
        os.makedirs(generated_image_dir, exist_ok=True)
        with open(os.path.join(generated_image_dir, filename), "wb") as image_file:
            image_file.write(image_bytes)
        return {
            "image_url": f"/api/images/{filename}",
            "model": "SD-Turbo",
            "prompt": request.prompt,
        }

    @router.get("/api/images/{filename}", include_in_schema=False)
    async def get_generated_image(filename: str) -> FileResponse:
        if not re.fullmatch(r"[a-f0-9]{32}\.png", filename):
            raise HTTPException(status_code=404, detail="Image not found.")
        image_path = os.path.join(generated_image_dir, filename)
        if not os.path.isfile(image_path):
            raise HTTPException(status_code=404, detail="Image not found.")
        return FileResponse(image_path, media_type="image/png")

    return router
