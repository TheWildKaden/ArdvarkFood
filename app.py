"""Stable ASGI entry point; application modules live under ``services.api``."""

from pathlib import Path

import httpx
from fastapi import FastAPI

from packages.image_generation import ImageGenerator
from services.api.app_factory import (
    DEFAULT_GENERATED_IMAGE_DIR,
    REPOSITORY_ROOT,
    create_app as _create_app,
)


ROOT = REPOSITORY_ROOT
GENERATED_IMAGE_DIR = str(DEFAULT_GENERATED_IMAGE_DIR)


def create_app(
    *,
    ai_transport: httpx.AsyncBaseTransport | None = None,
    image_generator: ImageGenerator | None = None,
    generated_image_dir: str | Path | None = None,
) -> FastAPI:
    return _create_app(
        ai_transport=ai_transport,
        image_generator=image_generator,
        generated_image_dir=generated_image_dir or GENERATED_IMAGE_DIR,
    )


app = create_app()
