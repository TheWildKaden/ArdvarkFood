from __future__ import annotations

import json
import subprocess
from pathlib import Path


def render_mermaid_files(root: Path, diagrams: list[tuple[Path, Path]]) -> None:
    renderer = root / "scripts" / "architecture" / "render_mermaid.mjs"
    if not renderer.is_file():
        raise RuntimeError(f"Mermaid renderer entry point is missing: {renderer}")
    request = [
        {"input": str(source.resolve()), "output": str(output.resolve())}
        for source, output in diagrams
    ]
    result = subprocess.run(
        ["node", str(renderer)],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        cwd=root,
    )
    if result.returncode:
        raise RuntimeError(
            "Mermaid rendering failed:\n"
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    for _, output in diagrams:
        if not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError(f"Mermaid CLI produced no SVG for {output}.")
