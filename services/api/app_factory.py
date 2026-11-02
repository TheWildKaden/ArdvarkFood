from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from packages.image_generation import ImageGenerator, LocalImageGenerator
from runtime.api.server import mount_runtime
from .routes import create_api_router


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WEBSITE_ROOT = REPOSITORY_ROOT / "website"
DEFAULT_GENERATED_IMAGE_DIR = REPOSITORY_ROOT / ".generated"


def create_app(
    *,
    ai_transport: httpx.AsyncBaseTransport | None = None,
    image_generator: ImageGenerator | None = None,
    generated_image_dir: str | Path | None = None,
) -> FastAPI:
    application = FastAPI(title="Ardvark")
    application.mount(
        "/assets",
        StaticFiles(directory=WEBSITE_ROOT / "assets"),
        name="static-assets",
    )
    local_generator = (
        image_generator if image_generator is not None else LocalImageGenerator()
    )
    image_dir = Path(
        generated_image_dir
        if generated_image_dir is not None
        else DEFAULT_GENERATED_IMAGE_DIR
    )

    @application.get("/", include_in_schema=False)
    async def home() -> FileResponse:
        return FileResponse(WEBSITE_ROOT / "index.html")

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

    mount_runtime(application)
    return application
