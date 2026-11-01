from __future__ import annotations

from typing import Any

from ..diagram import flowchart
from ..index import SourceIndex


PARSER_NAMES = {
    "parse_tagged_text",
    "_read_until_stop",
    "parse_tool_calls",
    "parse_message_from_completion_text",
    "render_message",
    "_encode_messages_text",
    "encode_messages",
    "encode_case",
    "bytes_to_unicode",
    "get_pairs",
    "bpe",
    "encode",
    "decode",
}


def analyze(index: SourceIndex, function_data: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        item
        for item in function_data["functions"]
        if item["path"].startswith("src/encoding/")
        or item["path"] == "src/encoder.py"
    ]
    selected = [
        item for item in candidates
        if item["name"] in PARSER_NAMES
    ]
    selected_names = {item["qualname"] for item in selected}
    edges = [
        (item["from"], item["to"], "detected call")
        for item in function_data["call_edges"]
        if item["from"] in selected_names and item["to"] in selected_names
    ]

    nodes = [
        (
            item["qualname"],
            f"{item['name']} · {item['path']}:{item['line']}",
        )
        for item in selected
    ]
    return {
        "components": [
            {"name": item["name"], "path": item["path"], "line": item["line"]}
            for item in selected
        ],
        "call_edges": [
            {"from": source, "to": target}
            for source, target, _ in edges
        ],
        "diagram": flowchart(
            "LR",
            nodes,
            edges,
            notes=[
                "Detected parsing and encoding functions from src/encoding/encoding.py and byte-pair encoder functions from src/encoder.py.",
                "No standalone lexer or parser package was detected. Role grouping is inferred from source names; arrows are direct local calls only.",
            ],
        ),
    }
