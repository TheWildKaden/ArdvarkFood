from __future__ import annotations

from typing import Any

from ..diagram import flowchart
from ..index import SourceIndex


def analyze(index: SourceIndex) -> dict[str, Any]:
    _, classes = index.python_symbols()
    for module in index.javascript_modules:
        for item in module["classes"]:
            classes.append(
                {
                    "name": item["name"],
                    "qualname": f"{index.relative(module['path'])}.{item['name']}",
                    "path": index.relative(module["path"]),
                    "line": item["line"],
                    "bases": [item["base"]] if item.get("base") else [],
                    "language": "JavaScript/TypeScript",
                    "confidence": "detected (Babel AST)",
                }
            )
    by_name: dict[str, list[dict[str, Any]]] = {}
    for item in classes:
        by_name.setdefault(item["name"], []).append(item)

    edges = []
    for item in classes:
        for base in item.get("bases", []):
            base_name = base.rsplit(".", 1)[-1]
            matches = by_name.get(base_name, [])
            if len(matches) == 1:
                edges.append((matches[0]["qualname"], item["qualname"], "detected inheritance"))

    selected_classes = classes
    if len(selected_classes) > 90:
        selected_classes = selected_classes[:90]
        selected_names = {item["qualname"] for item in selected_classes}
        edges = [edge for edge in edges if edge[0] in selected_names and edge[1] in selected_names]
    return {
        "classes": classes,
        "diagram": flowchart(
            "TB",
            [
                (
                    item["qualname"],
                    f"{item['name']} · {item['path']}:{item['line']}",
                )
                for item in selected_classes
            ],
            edges,
            notes=[
                "Only local base classes that resolve uniquely are connected; protocol and runtime relationships are not inferred as inheritance."
            ],
        ),
    }
