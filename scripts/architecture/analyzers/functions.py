from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from ..diagram import flowchart
from ..index import SourceIndex


def analyze(index: SourceIndex) -> dict[str, Any]:
    python_functions, _ = index.python_symbols()
    functions = list(python_functions)
    for module in index.javascript_modules:
        for function in module["functions"]:
            functions.append(
                {
                    **function,
                    "qualname": (
                        f"{index.relative(module['path'])}.{function['owner']}."
                        f"{function['name']}"
                        if function.get("owner")
                        else f"{index.relative(module['path'])}.{function['name']}"
                    ),
                    "path": index.relative(module["path"]),
                    "language": "JavaScript/TypeScript",
                    "confidence": "detected (Babel AST)",
                }
            )

    by_name: dict[str, list[dict[str, Any]]] = {}
    by_file_name: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for function in functions:
        by_name.setdefault(function["name"], []).append(function)
        by_file_name.setdefault(
            (function["path"], function["name"]), []
        ).append(function)
        if function.get("owner"):
            by_name.setdefault(f"{function['owner']}.{function['name']}", []).append(function)

    edges: set[tuple[str, str]] = set()
    for function in functions:
        for call in function.get("calls", []):
            target = call.get("target")
            resolved: dict[str, Any] | None = None
            if resolved is None and target:
                matches = by_name.get(target, [])
                matches = [
                    item
                    for item in matches
                    if item["language"] == function["language"]
                ]
                if len(matches) == 1:
                    resolved = matches[0]
            if resolved is None:
                expression = call.get("expression") or call.get("callee", "")
                name = call.get("name") or expression.split(".")[-1]
                if not expression or "." in expression:
                    continue
                matches = by_file_name.get((function["path"], name), [])
                if len(matches) == 1:
                    resolved = matches[0]
            if resolved is not None and resolved["qualname"] != function["qualname"]:
                edges.add((function["qualname"], resolved["qualname"]))

    degree = Counter()
    for source, target in edges:
        degree[source] += 1
        degree[target] += 1
    selected = {
        name
        for name, _ in degree.most_common(76)
    }
    if len(selected) < 2:
        selected.update(function["qualname"] for function in functions[:40])
    selected_edges = sorted(
        (source, target)
        for source, target in edges
        if source in selected and target in selected
    )
    function_lookup = {item["qualname"]: item for item in functions}
    nodes = [
        (
            name,
            f"{function_lookup[name]['name']} · {function_lookup[name]['path']}:{function_lookup[name]['line']}",
        )
        for name in sorted(selected)
        if name in function_lookup
    ]
    return {
        "functions": functions,
        "call_edges": [
            {"from": source, "to": target, "evidence": "direct call syntax"}
            for source, target in sorted(edges)
        ],
        "diagram": flowchart(
            "LR",
            nodes,
            [(source, target, "detected call") for source, target in selected_edges],
            notes=[
                "Edges resolve direct call syntax to a unique local function or an instance attribute assigned a local class.",
                "Unqualified calls resolve only within the same source file; dynamic dispatch, reflection, imported calls, unresolved names, and callbacks are omitted. Diagram is capped to the 76 most connected functions.",
            ],
        ),
    }
