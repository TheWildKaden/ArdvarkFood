from __future__ import annotations

import os
from pathlib import Path
import threading
import time
from typing import Any, Callable

from .compiler import ArtifactCompiler, CompilationError


class ArtifactWatcher:
    """Opt-in polling watcher; only configured JSON/JSONL files are compiled."""

    def __init__(
        self,
        directories: list[str | Path],
        output_directory: str | Path,
        *,
        compiler: ArtifactCompiler | None = None,
        interval_seconds: float = 1.0,
        exclusions: tuple[str, ...] = (".git", ".venv", "node_modules", "__pycache__"),
        on_build: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        if interval_seconds < 0.1:
            raise ValueError("Watcher interval must be at least 0.1 seconds.")
        self.directories = [Path(path).expanduser().resolve(strict=True) for path in directories]
        if any(not path.is_dir() for path in self.directories):
            raise ValueError("Every watch path must be a directory.")
        self.output_directory = Path(output_directory).expanduser().resolve()
        if any(
            self.output_directory == path or path in self.output_directory.parents
            for path in self.directories
        ):
            raise ValueError("Compiler output must be outside watched directories.")
        self.compiler = compiler or ArtifactCompiler()
        self.interval_seconds = interval_seconds
        self.exclusions = set(exclusions)
        self.on_build = on_build
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def scan_once(self) -> list[dict[str, Any]]:
        builds = []
        for directory in self.directories:
            for current, names, files in os.walk(directory, followlinks=False):
                names[:] = [
                    name
                    for name in names
                    if name not in self.exclusions and not (Path(current) / name).is_symlink()
                ]
                for filename in files:
                    source = Path(current) / filename
                    if source.suffix.lower() not in {".json", ".jsonl"} or source.is_symlink():
                        continue
                    relative = source.relative_to(directory)
                    output = (self.output_directory / relative).with_name(
                        relative.name + ".min"
                    )
                    output = output.with_suffix(output.suffix + source.suffix.lower())
                    try:
                        result = self.compiler.compile(source, output)
                    except (OSError, CompilationError) as error:
                        result = {
                            "source": str(source),
                            "status": "error",
                            "error": str(error),
                        }
                    if not result.get("cache_hit", False):
                        result["status"] = result.get("status", "built")
                        builds.append(result)
                        if self.on_build:
                            self.on_build(result)
        return builds

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()

        def watch() -> None:
            while not self._stop.is_set():
                self.scan_once()
                self._stop.wait(self.interval_seconds)

        self._thread = threading.Thread(target=watch, name="ardvark-artifact-watcher", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive():
                raise TimeoutError("Artifact watcher did not stop within the timeout.")
            self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
