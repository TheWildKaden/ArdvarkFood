import importlib
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse

from local_image_generator import ImageGenerator, LocalImageGenerator
from .routes import create_api_router


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GENERATED_IMAGE_DIR = REPOSITORY_ROOT / ".generated"


def create_app(
    *,
    ai_transport: httpx.AsyncBaseTransport | None = None,
    image_generator: ImageGenerator | None = None,
    generated_image_dir: str | Path | None = None,
) -> FastAPI:
    application = FastAPI(title="Ardvark")
    local_generator = image_generator or LocalImageGenerator()
    image_dir = Path(generated_image_dir or DEFAULT_GENERATED_IMAGE_DIR)

    @application.get("/", include_in_schema=False)
    async def home() -> FileResponse:
        return FileResponse(REPOSITORY_ROOT / "static" / "index.html")

    @application.get("/project", include_in_schema=False)
    async def project_site() -> FileResponse:
        return FileResponse(REPOSITORY_ROOT / "docs" / "index.html")

    application.include_router(
        create_api_router(
            ai_transport=ai_transport,
            image_generator=local_generator,
            generated_image_dir=str(image_dir),
        )
    )

    runtime_server = importlib.import_module("AI-Runtime.api.server")
    runtime_server.mount_runtime(application)
    return application
