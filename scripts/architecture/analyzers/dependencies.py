from __future__ import annotations

import ast
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


def analyze(root: Path, index: Any) -> dict[str, Any]:
    manifests: dict[str, list[str]] = {}
    for path in sorted(root.glob("requirements*.txt")):
        manifests[path.relative_to(root).as_posix()] = _read_requirements(path)
    runtime_requirements = root / "AI-Runtime" / "requirements.txt"
    if runtime_requirements.is_file():
        manifests["AI-Runtime/requirements.txt"] = _read_requirements(
            runtime_requirements
        )

    package_path = root / "package.json"
    package_json: dict[str, Any] = {}
    if package_path.is_file():
        package_json = json.loads(package_path.read_text(encoding="utf-8"))
        for section in ("dependencies", "devDependencies", "optionalDependencies"):
            values = package_json.get(section, {})
            if values:
                manifests[f"package.json:{section}"] = sorted(values)

    nodes: list[tuple[str, str]] = []
    edges: list[tuple[str, str, str | None]] = []
    for manifest, dependencies in manifests.items():
        manifest_id = f"manifest_{manifest}"
        nodes.append((manifest_id, f"{manifest} ({len(dependencies)} packages)"))
        for dependency in dependencies[:14]:
            dependency_id = f"dep_{manifest}_{dependency}"
            nodes.append((dependency_id, dependency))
            edges.append((manifest_id, dependency_id, "declares"))

    declared = {
        dependency.casefold()
        for values in manifests.values()
        for dependency in values
    }
    js_imports = {
        imported["source"]
        for module in index.javascript_modules
        for imported in module["imports"]
    }
    python_imports = {
        alias.name.split(".", 1)[0]
        for module in index.python_modules.values()
        for node in ast.walk(module.tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    python_imports.update(
        node.module.split(".", 1)[0]
        for module in index.python_modules.values()
        for node in ast.walk(module.tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    stack = []
    if index.python_modules:
        stack.append("Python")
    for package_name, title in (
        ("fastapi", "FastAPI"),
        ("pydantic", "Pydantic"),
        ("httpx", "httpx"),
        ("llama-cpp-python", "llama.cpp Python binding"),
        ("torch", "PyTorch"),
        ("diffusers", "Diffusers"),
    ):
        if package_name in declared or package_name.replace("-", "_") in python_imports:
            stack.append(title)
    if "react" in js_imports:
        stack.append("React source")
    if "fastify" in js_imports:
        stack.append("Fastify source")
    if "sqlite3" in python_imports or "better-sqlite3" in js_imports:
        stack.append("SQLite")
    if package_json:
        stack.append("Node.js")
    if "@mermaid-js/mermaid-cli" in package_json.get("devDependencies", {}):
        stack.append("Mermaid CLI")
    if "@babel/parser" in package_json.get("devDependencies", {}):
        stack.append("Babel parser")
    return {
        "manifests": manifests,
        "package": package,
        "stack": stack,
        "diagram": flowchart(
            "LR",
            nodes,
            edges,
            notes=[
                "Full manifest inventory is in architecture.json. This overview caps each manifest at 14 packages.",
                "Manifest declarations and imports are detected facts; declaration does not prove a feature is runnable.",
            ],
        ),
    }
