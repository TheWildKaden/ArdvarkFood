from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..diagram import flowchart


def analyze(root: Path) -> dict[str, Any]:
    package_path = root / "package.json"
    package = json.loads(package_path.read_text(encoding="utf-8")) if package_path.is_file() else {}
    scripts = package.get("scripts", {})
    nodes: list[tuple[str, str]] = []
    edges: list[tuple[str, str, str | None]] = []
    for name, command in sorted(scripts.items()):
        script_node = f"npm_{name}"
        nodes.append((script_node, f"npm {name}: {command}"))
        match = re.search(r"scripts/[\w./-]+\.(?:mjs|js|sh)", command)
        if match:
            file_node = match.group(0)
            nodes.append((file_node, file_node))
            edges.append((script_node, file_node, "script target detected"))

    workflows = []
    workflow_root = root / ".github" / "workflows"
    if workflow_root.is_dir():
        for path in sorted(workflow_root.glob("*.yml")) + sorted(workflow_root.glob("*.yaml")):
            text = path.read_text(encoding="utf-8")
            name_match = re.search(r"(?m)^name:\s*(.+)$", text)
            name = name_match.group(1).strip().strip('"\'') if name_match else path.stem
            workflow_id = f"workflow_{path.stem}"
            workflows.append({"name": name, "path": path.relative_to(root).as_posix()})
            nodes.append((workflow_id, f"{name} · {path.relative_to(root).as_posix()}"))
            commands = re.findall(r"(?m)^\s+run:\s*[|>]?\s*(.+)?$", text)
            for command in commands:
                command = (command or "").strip().strip('"\'')
                if not command:
                    continue
                command_node = f"{workflow_id}_{len(edges)}"
                nodes.append((command_node, f"CI command: {command}"))
                edges.append((workflow_id, command_node, "run step detected"))
                npm_match = re.search(r"npm (?:run )?([\w:-]+)", command)
                if npm_match and f"npm_{npm_match.group(1)}" in {
                    item[0] for item in nodes
                }:
                    edges.append((command_node, f"npm_{npm_match.group(1)}", "invokes"))

    generation_files = [
        "scripts/generate_architecture.py",
        "scripts/architecture/",
        ".github/workflows/update-architecture.yml",
        "docs/architecture/",
    ]
    for value in generation_files:
        if (root / value).exists():
            nodes.append((value, value))
    if ".github/workflows/update-architecture.yml" in generation_files and (
        root / ".github/workflows/update-architecture.yml"
    ).is_file():
        workflow_id = "workflow_update_architecture"
        edges.append((workflow_id, "scripts/generate_architecture.py", "runs generator"))
        edges.append((workflow_id, "docs/architecture/", "writes generated assets"))

    return {
        "package_scripts": scripts,
        "workflows": workflows,
        "diagram": flowchart(
            "LR",
            nodes,
            edges,
            notes=[
                "Build entries come from package.json, workflow run commands, and generated architecture paths; deployment results are not inferred."
            ],
        ),
    }
