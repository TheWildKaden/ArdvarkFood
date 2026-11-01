from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..diagram import flowchart


def _read_requirements(path: Path) -> list[str]:
    raw = path.read_bytes()
    text = raw.decode("utf-16") if b"\x00" in raw[:100] else raw.decode("utf-8-sig")
    packages = []
    for line in text.splitlines():
        match = re.match(r"\s*([A-Za-z0-9_.-]+)(?=\s|[<>=!~;\[])",
                         line.split("#", 1)[0])
        if match:
            packages.append(match.group(1))
    return packages


def analyze(root: Path) -> dict[str, Any]:
    manifests: dict[str, list[str]] = {}
    for path in sorted(root.glob("requirements*.txt")):
        manifests[path.relative_to(root).as_posix()] = _read_requirements(path)
    runtime_requirements = root / "AI-Runtime" / "requirements.txt"
    if runtime_requirements.is_file():
        manifests["AI-Runtime/requirements.txt"] = _read_requirements(
            runtime_requirements
        )

    package_path = root / "package.json"
    package: dict[str, Any] = {}
    if package_path.is_file():
        package = json.loads(package_path.read_text(encoding="utf-8"))
        for section in ("dependencies", "devDependencies", "optionalDependencies"):
            values = package.get(section, {})
            if values:
                manifests[f"package.json:{section}"] = sorted(values)

    nodes: list[tuple[str, str]] = []
    edges: list[tuple[str, str, str | None]] = []
    for manifest, dependencies in manifests.items():
        manifest_id = f"manifest_{manifest}"
        nodes.append((manifest_id, manifest))
        for dependency in dependencies:
            dependency_id = f"dep_{manifest}_{dependency}"
            nodes.append((dependency_id, dependency))
            edges.append((manifest_id, dependency_id, "declares"))

    stack = sorted(
        {
            "Python",
            "FastAPI",
            "Pydantic",
            "httpx",
            "React",
            "Fastify",
            "Node.js",
            "Mermaid CLI",
            "Babel parser",
        }
    )
    return {
        "manifests": manifests,
        "package": package,
        "stack": stack,
        "diagram": flowchart(
            "LR",
            nodes,
            edges,
            notes=[
                "Detected from requirements files and package.json; package presence does not prove runtime import."
            ],
        ),
    }
