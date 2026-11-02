from __future__ import annotations

import re
from collections.abc import Iterable


def node_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if not safe or safe[0].isdigit():
        safe = f"n_{safe}"
    return safe


def label(value: str, limit: int = 78) -> str:
    compact = " ".join(str(value).replace("\r", " ").replace("\n", " ").split())
    if len(compact) > limit:
        compact = compact[: limit - 1] + "…"
    return compact.replace('"', "'").replace("|", "/")


def flowchart(
    direction: str,
    nodes: Iterable[tuple[str, str]],
    edges: Iterable[tuple[str, str, str | None]],
    *,
    notes: Iterable[str] = (),
) -> str:
    lines = [f"flowchart {direction}"]
    for identifier, text in nodes:
        lines.append(f'  {node_id(identifier)}["{label(text)}"]')
    for source, target, edge_label in edges:
        suffix = f'|"{label(edge_label, 48)}"|' if edge_label else ""
        lines.append(f"  {node_id(source)} -->{suffix} {node_id(target)}")
    for index, note in enumerate(notes):
        identifier = f"analysis_note_{index}"
        lines.append(f'  {identifier}["{label(note, 110)}"]')
        lines.append(f"  class {identifier} note")
    if notes:
        lines.append("  classDef note fill:#fff7d6,stroke:#b38b00,color:#333")
    return "\n".join(lines) + "\n"
