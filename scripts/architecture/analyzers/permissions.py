from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from ..diagram import flowchart
from ..index import SourceIndex


def analyze(index: SourceIndex, runtime_data: dict[str, Any]) -> dict[str, Any]:
    permission_fields: set[str] = set()
    approval_actions: set[str] = set()
    for path, module in index.python_modules.items():
        if path.name != "permission_manager.py":
            continue
        for item in ast.walk(module.tree):
            if isinstance(item, ast.Attribute) and isinstance(item.value, ast.Name):
                if item.value.id in {"self", "definition"}:
                    permission_fields.add(item.attr)
            if isinstance(item, ast.Call):
                call_name = SourceIndex._name(item.func)
                if call_name in {"notify", "asyncio.wait_for", "future.set_result"}:
                    approval_actions.add(call_name)

    nodes = [
        ("Tool Call", "Model-proposed tool call"),
        ("Tool Executor", "ToolExecutor.execute"),
        ("Tool Registry", "ToolRegistry.get / registered handler"),
        ("Permission Manager", "PermissionManager.authorize"),
        ("Denied", "explicitly denied permission"),
        ("Auto Approved", "server-configured auto approval"),
        ("Approval Required", "approval request + decision wait"),
        ("Handler", "validated tool handler"),
        ("Audit", "tool event and audit record"),
    ]
    edges = [
        ("Tool Call", "Tool Executor", "detected dispatch"),
        ("Tool Executor", "Tool Registry", "name lookup"),
        ("Tool Executor", "Permission Manager", "authorization gate"),
        ("Permission Manager", "Denied", "denied permissions"),
        ("Permission Manager", "Auto Approved", "auto-approved permissions"),
        ("Permission Manager", "Approval Required", "approval-required permissions"),
        ("Auto Approved", "Handler", "authorization passes"),
        ("Approval Required", "Handler", "only after approval"),
        ("Handler", "Audit", "execution outcome"),
    ]
    return {
        "permission_manager_fields": sorted(permission_fields),
        "approval_calls": sorted(approval_actions),
        "runtime_edges": runtime_data["execution_edges"],
        "diagram": flowchart(
            "LR",
            nodes,
            edges,
            notes=[
                "The policy branches and gate sequence are inferred from PermissionManager.authorize and ToolExecutor.execute.",
                "The LLM supplies arguments; server-side schema validation and PermissionManager authorization occur before handlers run.",
            ],
        ),
    }
