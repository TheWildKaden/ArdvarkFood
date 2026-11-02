"""Small async client for the runtime API used by terminal workbench panes."""

from __future__ import annotations

import os
from typing import Any

import httpx


class RuntimeAPIError(RuntimeError):
    pass


async def request_json(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    base_url = os.getenv("ARDVARK_API_URL", "http://127.0.0.1:8000").rstrip("/")
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
            response = await client.request(
                method, path, json=payload, params=params
            )
        if response.is_error:
            try:
                details = response.json().get("detail", response.text)
            except ValueError:
                details = response.text
            raise RuntimeAPIError(f"Runtime API {response.status_code}: {details}")
        return response.json()
    except httpx.RequestError as error:
        raise RuntimeAPIError(
            f"Cannot reach the runtime API at {base_url}. Start it with `python -m cli serve`."
        ) from error
