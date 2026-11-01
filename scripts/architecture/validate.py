from __future__ import annotations

import html
import json
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from .render import render_mermaid_files


DIAGRAM_NAMES = (
    "project-structure",
    "dependencies",
    "modules",
    "call-graph",
    "class-relationships",
    "lexer-parser",
    "api-architecture",
    "llm-runtime",
    "agent-execution",
    "permissions",
    "storage",
    "build-pipelines",
)


def _validate_json(path: Path) -> None:
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid JSON asset {path}: {error}") from error


def _validate_svg(path: Path) -> None:
    try:
        tree = ET.parse(path)
    except (OSError, ET.ParseError) as error:
        raise ValueError(f"Invalid SVG {path}: {error}") from error
    root = tree.getroot()
    if not root.tag.endswith("svg"):
        raise ValueError(f"SVG asset has unexpected root element: {path}")
    for element in root.iter():
        if element.tag.endswith("script"):
            raise ValueError(f"SVG must not contain executable script: {path}")
        if any(attribute.lower().startswith("on") for attribute in element.attrib):
            raise ValueError(f"SVG must not contain event-handler attributes: {path}")


def _markdown_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        title = re.sub(r"<[^>]*>", "", match.group(1))
        title = re.sub(r"`([^`]*)`", r"\1", title)
        anchor = re.sub(r"[^\w -]", "", title.casefold()).strip()
        anchor = re.sub(r"[\s]+", "-", anchor)
        count = counts.get(anchor, 0)
        counts[anchor] = count + 1
        anchors.add(anchor if count == 0 else f"{anchor}-{count}")
    return anchors


def _validate_readme_links(root: Path) -> None:
    readme = root / "README.md"
    text = readme.read_text(encoding="utf-8")
    links = re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", text)
    links.extend(re.findall(r"""(?:href|src)=["']([^"']+)["']""", text))
    for raw_link in links:
        target = html.unescape(raw_link.strip())
        if not target or target.startswith(("http://", "https://", "mailto:", "data:", "#")):
            continue
        target = target.split("#", 1)[0].split("?", 1)[0]
        fragment_match = re.search(r"#([^#]+)$", raw_link)
        fragment = html.unescape(fragment_match.group(1)) if fragment_match else None
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1]
        destination = (root / target).resolve()
        if not destination.exists():
            raise ValueError(f"README links to missing local path: {raw_link}")
        if fragment and destination.is_file() and destination.suffix.lower() in {".md", ".markdown"}:
            if fragment not in _markdown_anchors(destination):
                raise ValueError(f"README links to missing heading anchor: {raw_link}")


def _validate_mermaid(root: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="ardvark-mermaid-check-") as directory:
        temp = Path(directory)
        render_queue: list[tuple[Path, Path]] = []
        for name in DIAGRAM_NAMES:
            source = root / "docs" / "architecture" / f"{name}.mmd"
            if not source.is_file():
                raise ValueError(f"Missing Mermaid source file: {source}")
            output = temp / f"{name}.svg"
            render_queue.append((source, output))
        render_mermaid_files(root, render_queue)


def validate_generated(root: Path, *, require_mermaid: bool) -> None:
    architecture_dir = root / "docs" / "architecture"
    for relative in (
        "architecture.json",
        "assets/contributors.json",
        "assets/statistics.json",
    ):
        path = architecture_dir / relative
        if not path.is_file():
            raise ValueError(f"Missing generated JSON asset: {path}")
        _validate_json(path)

    svgs = sorted(architecture_dir.rglob("*.svg"))
    if not svgs:
        raise ValueError("No repository-local SVG previews or contributor avatars found.")
    for path in svgs:
        _validate_svg(path)
    _validate_readme_links(root)
    if require_mermaid:
        _validate_mermaid(root)
