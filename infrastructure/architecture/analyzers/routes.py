from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from ..diagram import flowchart
from ..index import SourceIndex


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def analyze(index: SourceIndex) -> dict[str, Any]:
    routes: list[dict[str, Any]] = []
    for path, module in index.python_modules.items():
        prefix = ""
        for node in ast.walk(module.tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            if not isinstance(value, ast.Call) or SourceIndex._name(value.func) != "APIRouter":
                continue
            prefix_arg = next(
                (keyword.value for keyword in value.keywords if keyword.arg == "prefix"),
                None,
            )
            prefix = _literal_string(prefix_arg) or ""
        for node in ast.walk(module.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                    continue
                method = decorator.func.attr.lower()
                if method not in HTTP_METHODS or not decorator.args:
                    continue
                route_path = _literal_string(decorator.args[0])
                if route_path is None:
                    continue
                full_path = f"{prefix.rstrip('/')}/{route_path.lstrip('/')}" if prefix else route_path
                routes.append(
                    {
                        "method": method.upper(),
                        "path": full_path,
                        "handler": node.name,
                        "source": index.relative(path),
                        "line": node.lineno,
                        "framework": "FastAPI",
                        "confidence": "detected (Python AST decorator)",
                    }
                )

    for module in index.javascript_modules:
        for route in module.get("routes", []):
            routes.append(
                {
                    **route,
                    "framework": "Fastify (method call syntax)",
                    "handler": "route callback",
                    "confidence": "detected (Babel AST call)",
                }
            )

    routes.sort(key=lambda item: (item["framework"], item["path"], item["method"]))
    nodes: list[tuple[str, str]] = []
    edges: list[tuple[str, str, str | None]] = []
    apps: dict[str, str] = {}
    for route in routes:
        app_id = route["framework"]
        if app_id not in apps:
            apps[app_id] = app_id
            nodes.append((app_id, app_id))
        route_id = f"{route['method']}_{route['path']}_{route['source']}"
        nodes.append(
            (
                route_id,
                f"{route['method']} {route['path']} → {route['handler']} ({route['source']}:{route['line']})",
            )
        )
        edges.append((app_id, route_id, "detected route"))

    return {
        "routes": routes,
        "diagram": flowchart(
            "LR",
            nodes,
            edges,
            notes=[
                "Only literal HTTP paths found in FastAPI decorators or JavaScript HTTP-method calls are listed.",
                "Dynamically composed paths and mounts may not appear; detected paths are not an OpenAPI contract check.",
            ],
        ),
    }
