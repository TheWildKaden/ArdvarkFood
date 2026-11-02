from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from ..diagram import flowchart
from ..index import SourceIndex


RUNTIME_CLASSES = {
    "AgentRuntime",
    "AgentLoop",
    "ContextBuilder",
    "Planner",
    "InferenceEngine",
    "ModelManager",
    "LlamaCppAdapter",
    "OpenAICompatibleAdapter",
    "InputRouter",
    "ToolRegistry",
    "ToolExecutor",
    "PermissionManager",
    "MCPManager",
    "MemoryManager",
    "StorageManager",
}


def _constructor_edges(index: SourceIndex) -> list[tuple[str, str, str]]:
    result: list[tuple[str, str, str]] = []
    for path, module in index.python_modules.items():
        module_name = index.module_name(path)
        for class_node in (item for item in ast.walk(module.tree) if isinstance(item, ast.ClassDef)):
            for child in class_node.body:
                if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for statement in ast.walk(child):
                    if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
                        continue
                    value = statement.value
                    if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Name):
                        continue
                    targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                    if any(
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"
                        for target in targets
                    ):
                        result.append(
                            (
                                f"{module_name}.{class_node.name}",
                                value.func.id,
                                f"constructor at {index.relative(path)}:{statement.lineno}",
                            )
                        )
    return result


def _adapter_edges(index: SourceIndex) -> list[tuple[str, str, str]]:
    result: list[tuple[str, str, str]] = []
    for path, module in index.python_modules.items():
        if path.name != "model_manager.py":
            continue
        for node in ast.walk(module.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != "_make_adapter":
                continue
            for imported in ast.walk(node):
                if isinstance(imported, ast.ImportFrom):
                    for alias in imported.names:
                        if alias.name.endswith("Adapter"):
                            result.append(
                                (
                                    "ModelManager",
                                    alias.name,
                                    f"explicit backend import at {index.relative(path)}:{imported.lineno}",
                                )
                            )
    return result


def _execution_edges(index: SourceIndex) -> list[tuple[str, str, str]]:
    python_functions, _ = index.python_symbols()
    class_names = {
        item.name
        for _, module in index.python_modules.items()
        for item in ast.walk(module.tree)
        if isinstance(item, ast.ClassDef)
    }
    method_names = {
        (function["owner"], function["name"]): function
        for function in python_functions
        if function.get("owner")
    }
    edges: set[tuple[str, str, str]] = set()
    for function in python_functions:
        owner = function.get("owner")
        if owner not in RUNTIME_CLASSES:
            continue
        for call in function["calls"]:
            target = call.get("target")
            if not target or "." not in target:
                continue
            target_owner, target_method = target.rsplit(".", 1)
            if target_owner in class_names and (target_owner, target_method) in method_names:
                edges.add(
                    (
                        f"{owner}.{function['name']}",
                        target,
                        f"direct call at {function['path']}:{call['line']}",
                    )
                )
    return sorted(edges)


def analyze(index: SourceIndex) -> dict[str, Any]:
    constructor_edges = [
        edge for edge in _constructor_edges(index)
        if edge[0].rsplit(".", 1)[-1] in RUNTIME_CLASSES
        and edge[1] in RUNTIME_CLASSES
    ]
    adapter_edges = _adapter_edges(index)
    call_edges = _execution_edges(index)

    nodes: dict[str, str] = {}
    edges: list[tuple[str, str, str | None]] = []
    for source, target, evidence in constructor_edges:
        source_id = source.rsplit(".", 1)[-1]
        nodes[source_id] = source_id
        nodes[target] = target
        edges.append((source_id, target, "constructs"))
    for source, target, evidence in adapter_edges:
        nodes[source] = source
        nodes[target] = target
        edges.append((source, target, "explicit backend import"))
    for source, target, evidence in call_edges:
        source_id = source.rsplit(".", 1)[0].split(".")[-1]
        target_id = target.rsplit(".", 1)[0].split(".")[-1]
        nodes[source_id] = source_id
        nodes[target_id] = target_id
        edges.append((source_id, target_id, "direct call"))

    return {
        "components": sorted(nodes),
        "constructor_edges": [
            {"from": source, "to": target, "evidence": evidence}
            for source, target, evidence in constructor_edges
        ],
        "adapter_edges": [
            {"from": source, "to": target, "evidence": evidence}
            for source, target, evidence in adapter_edges
        ],
        "execution_edges": [
            {"from": source, "to": target, "evidence": evidence}
            for source, target, evidence in call_edges
        ],
        "diagram": flowchart(
            "LR",
            list(nodes.items()),
            edges,
            notes=[
                "Composition edges come from self-attribute constructor assignments; adapter edges come from imports in ModelManager._make_adapter.",
                "Call edges are direct calls resolved using annotated or constructed instance types; no external model is loaded during analysis.",
            ],
        ),
    }
