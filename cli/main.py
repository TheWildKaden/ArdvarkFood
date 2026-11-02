from __future__ import annotations

import argparse
import os
from collections.abc import Sequence


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("port must be an integer") from error
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ardvark",
        description="Run the Ardvark web application and agent API.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="serve the web application")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=_port, default=os.getenv("PORT", "8000"))
    serve.add_argument("--reload", action="store_true")
    arguments = parser.parse_args(argv)

    try:
        import uvicorn
    except ImportError as error:
        raise SystemExit(
            "Uvicorn is required to serve Ardvark. Install dependencies with "
            "`python -m pip install -r requirements.txt`."
        ) from error

    uvicorn.run(
        "app:app",
        host=arguments.host,
        port=arguments.port,
        reload=arguments.reload,
    )
    return 0
