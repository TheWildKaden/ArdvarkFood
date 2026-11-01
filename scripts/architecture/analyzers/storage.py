from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..diagram import flowchart
from ..index import SourceIndex


def analyze(index: SourceIndex, runtime_data: dict[str, Any]) -> dict[str, Any]:
    storage_path = index.root / "AI-Runtime" / "storage" / "storage_manager.py"
    source = storage_path.read_text(encoding="utf-8") if storage_path.is_file() else ""
    tables = sorted(set(re.findall(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+([A-Za-z_][A-Za-z0-9_]*)",
        source,
        flags=re.IGNORECASE,
    )))

    consumers: set[str] = set()
    methods: set[str] = set()
    for edge in runtime_data["execution_edges"]:
        target = edge["to"]
        if target.startswith("StorageManager."):
            consumers.add(edge["from"].split(".", 1)[0])
            methods.add(target.rsplit(".", 1)[-1])

    nodes: list[tuple[str, str]] = [("SQLite", "StorageManager → SQLite")]
    edges: list[tuple[str, str, str | None]] = []
    for consumer in sorted(consumers):
        nodes.append((consumer, consumer))
        edges.append((consumer, "SQLite", "direct storage calls"))
    for method in sorted(methods):
        nodes.append((f"StorageManager.{method}", f"StorageManager.{method}"))
        edges.append(("SQLite", f"StorageManager.{method}", "method persists/reads state"))
    for table in tables:
        nodes.append((table, f"SQLite table: {table}"))
        edges.append(("SQLite", table, "CREATE TABLE detected"))

    return {
        "database": "SQLite (detected from storage_manager.py)",
        "tables": tables,
        "storage_methods": sorted(methods),
        "diagram": flowchart(
            "LR",
            nodes,
            edges,
            notes=[
                "Table names come from CREATE TABLE statements; consumer edges come from uniquely resolved calls to StorageManager methods."
            ],
        ),
    }
