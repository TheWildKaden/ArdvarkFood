from __future__ import annotations

import ast
import importlib.util
from collections import Counter
from pathlib import Path
from typing import Any

from ..diagram import flowchart
from ..index import SourceIndex


def _python_import_targets(index: SourceIndex, path: Path, tree: ast.Module) -> set[Path]:
    module_lookup: dict[str, Path] = {}
    for module_path in index.python_modules:
        module_lookup[index.module_name(module_path)] = module_path
    package = index.module_name(path)
    if path.stem != "__init__":
        package = package.rpartition(".")[0]
    targets: set[Path] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = []
            base = node.module or ""
            if node.level:
                try:
                    base = importlib.util.resolve_name("." * node.level + base, package)
                except (ImportError, ValueError):
                    continue
            if base:
                names.append(base)
            names.extend(f"{base}.{alias.name}" for alias in node.names if alias.name != "*")
        else:
            continue
        for name in names:
            target = module_lookup.get(name)
            if target is None:
                target = module_lookup.get(name.split(".", 1)[0])
            if target is not None and target != path:
                targets.add(target)
    return targets


def _component(path: str) -> str:
    if path.startswith("AI-Runtime/"):
        return "AI-Runtime"
    if path.startswith("src/web/"):
        return "FastAPI (src/web)"
    if path.startswith("src/encoding/"):
        return "Message encoding"
    if path.startswith("frontend/src/client/"):
        return "Frontend client"
    if path.startswith("frontend/src/server/"):
        return "Frontend server"
    if path.startswith("scripts/architecture/"):
        return "Architecture generator"
    return path.split("/", 1)[0] if "/" in path else "Repository root"


def analyze(index: SourceIndex) -> dict[str, Any]:
    groups: Counter[str] = Counter()
    edges: Counter[tuple[str, str]] = Counter()
    modules: list[dict[str, Any]] = []
    for path, module in index.python_modules.items():
        source = index.relative(path)
        group = _component(source)
        groups[group] += 1
        modules.append({"path": source, "language": "Python", "group": group})
        for target in _python_import_targets(index, path, module.tree):
            destination = _component(index.relative(target))
            if destination != group:
                edges[(group, destination)] += 1

    javascript_paths = {
        Path(record["path"]).resolve(): record for record in index.javascript_modules
    }
    javascript_lookup = set(javascript_paths)
    for path, record in javascript_paths.items():
        source = index.relative(path)
        group = _component(source)
        groups[group] += 1
        modules.append({"path": source, "language": "JavaScript/TypeScript", "group": group})
        for imported in record["imports"]:
            specifier = imported["source"]
            if not specifier.startswith("."):
                continue
            candidate = (path.parent / specifier).resolve()
            options = [candidate]
            if not candidate.suffix:
                options.extend(
                    candidate.with_suffix(suffix)
                    for suffix in (".js", ".jsx", ".mjs", ".ts", ".tsx")
                )
                options.extend(candidate / f"index{suffix}" for suffix in (".js", ".jsx"))
            destination_path = next((item for item in options if item in javascript_lookup), None)
            if destination_path is None:
                continue
            destination = _component(index.relative(destination_path))
            if destination != group:
                edges[(group, destination)] += 1

    component_nodes = [(name, f"{name} ({count} source files)") for name, count in sorted(groups.items())]
    edge_data = [
        (source, target, f"{count} detected imports")
        for (source, target), count in sorted(edges.items())
    ]
    return {
        "modules": sorted(modules, key=lambda item: item["path"]),
        "groups": dict(sorted(groups.items())),
        "edges": [
            {"from": source, "to": target, "imports": count}
            for (source, target), count in sorted(edges.items())
        ],
        "diagram": flowchart(
            "LR",
            component_nodes,
            edge_data,
            notes=["Edges are resolved relative/local imports detected by Python AST or Babel parser."],
        ),
    }
