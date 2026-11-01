from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import contributors
from .analyzers import (
    build,
    classes,
    compiler,
    dependencies,
    functions,
    modules,
    permissions,
    routes,
    runtime,
    storage,
)
from .diagram import flowchart
from .index import SourceIndex
from .validate import validate_generated


DIAGRAM_TITLES = [
    ("project-structure", "Project structure"),
    ("dependencies", "Declared dependencies"),
    ("modules", "Module and package imports"),
    ("call-graph", "Detected local call graph"),
    ("class-relationships", "Class inheritance"),
    ("lexer-parser", "Message lexer/parser and encoder"),
    ("api-architecture", "Detected API routes"),
    ("llm-runtime", "LLM and model runtime"),
    ("agent-execution", "Agent execution loop"),
    ("permissions", "Tool permission gates"),
    ("storage", "Persistent runtime storage"),
    ("build-pipelines", "Build and deployment pipelines"),
]


def _project_structure(index: SourceIndex, module_data: dict[str, Any]) -> str:
    nodes: list[tuple[str, str]] = [("root", "ArdvarkFood repository")]
    edges: list[tuple[str, str, str | None]] = []
    components = dict(module_data["groups"])
    for path in ("docs", "static", "tests", "frontend", "AI-Runtime"):
        if (index.root / path).is_dir():
            components.setdefault(path, 0)
    for component, count in sorted(components.items()):
        nodes.append((component, f"{component} ({count} analyzed source files)"))
        edges.append(("root", component, "directory/component"))
    for filename in (
        "app.py",
        "local_image_generator.py",
        "README.md",
        "package.json",
        "requirements.txt",
    ):
        if (index.root / filename).is_file():
            nodes.append((filename, filename))
            edges.append(("root", filename, "repository file"))
    return flowchart(
        "TB",
        nodes,
        edges,
        notes=[
            "Directory membership and source-file counts are detected from the checkout; component roles come from paths and imports."
        ],
    )


def _runtime_diagrams(
    runtime_data: dict[str, Any],
    permission_data: dict[str, Any],
) -> tuple[str, str]:
    runtime_nodes = [
        ("Application", "app.py → src/web/app_factory.py"),
        ("AgentRuntime", "AgentRuntime"),
        ("AgentLoop", "AgentLoop"),
        ("ContextBuilder", "ContextBuilder"),
        ("InferenceEngine", "InferenceEngine"),
        ("ModelManager", "ModelManager"),
        ("LlamaCppAdapter", "LlamaCppAdapter"),
        ("OpenAICompatibleAdapter", "OpenAICompatibleAdapter"),
        ("InputRouter", "InputRouter"),
        ("ToolRegistry", "ToolRegistry"),
        ("ToolExecutor", "ToolExecutor"),
        ("PermissionManager", "PermissionManager"),
        ("MCPManager", "MCPManager"),
        ("MemoryManager", "MemoryManager"),
        ("StorageManager", "StorageManager"),
    ]
    runtime_edges: list[tuple[str, str, str | None]] = []
    for item in runtime_data["constructor_edges"]:
        owner = item["from"].rsplit(".", 1)[-1]
        if owner in {"AgentRuntime", "AgentLoop"}:
            runtime_edges.append((owner, item["to"], "constructor detected"))
    for item in runtime_data["adapter_edges"]:
        runtime_edges.append((item["from"], item["to"], "backend branch import"))
    runtime_edges.extend(
        (item["from"].split(".", 1)[0], item["to"].split(".", 1)[0], "direct call")
        for item in runtime_data["execution_edges"]
        if item["from"].split(".", 1)[0] in {"AgentRuntime", "AgentLoop"}
        and item["to"].split(".", 1)[0] in {
            "AgentLoop",
            "ContextBuilder",
            "InferenceEngine",
            "ModelManager",
            "ToolExecutor",
            "StorageManager",
            "PermissionManager",
            "ToolRegistry",
        }
    )
    runtime_edges.append(("Application", "AgentRuntime", "lifespan mount detected"))
    runtime_diagram = flowchart(
        "LR",
        runtime_nodes,
        runtime_edges,
        notes=[
            "Model loading/inference and agent orchestration are separate source modules; arrows are extracted from constructors, imports, and direct calls."
        ],
    )

    flow_nodes = [
        ("User", "User message + attachments"),
        ("AgentRuntime.start", "AgentRuntime.start"),
        ("AgentLoop.run", "AgentLoop.run"),
        ("ContextBuilder.build", "ContextBuilder.build"),
        ("InferenceEngine", "InferenceEngine.generate / stream"),
        ("AgentDecision", "Tool calls present? (branch in AgentLoop.run)"),
        ("ToolExecutor.execute", "ToolExecutor.execute"),
        ("PermissionManager.authorize", "PermissionManager.authorize"),
        ("ToolHandler", "Registered tool handler"),
        ("ToolResult", "Tool result appended to model context"),
        ("Final", "Final assistant response persisted"),
    ]
    known_execution_edges = {
        (item["from"].rsplit(".", 1)[0], item["to"].rsplit(".", 1)[0])
        for item in runtime_data["execution_edges"]
    }
    flow_edges = [
        ("User", "AgentRuntime.start", "start execution"),
        ("AgentRuntime.start", "AgentLoop.run", "await direct call"),
        ("AgentLoop.run", "ContextBuilder.build", "build request context"),
        ("AgentLoop.run", "InferenceEngine", "generate/stream via helper"),
        ("AgentLoop.run", "AgentDecision", "inspect GenerationResponse"),
        ("AgentDecision", "ToolExecutor.execute", "tool_calls non-empty"),
        ("ToolExecutor.execute", "PermissionManager.authorize", "before handler"),
        ("PermissionManager.authorize", "ToolHandler", "policy permits"),
        ("ToolHandler", "ToolResult", "serialize result"),
        ("ToolResult", "AgentLoop.run", "follow-up step"),
        ("AgentDecision", "Final", "no tool calls"),
    ]
    return runtime_diagram, flowchart(
        "LR",
        flow_nodes,
        flow_edges,
        notes=[
            "Decision and loop-back labels summarize the explicit loop/branch in AgentLoop.run; handlers execute only after ToolExecutor authorization.",
            f"Detected orchestration call links: {len(known_execution_edges)} unique source-resolved owner/method pairs.",
        ],
    )


def _architecture_readme_section() -> str:
    pieces = [
        "The diagrams below are local SVG previews; every one links to its editable Mermaid source."
    ]
    for name, title in DIAGRAM_TITLES:
        mmd = f"docs/architecture/{name}.mmd"
        svg = f"docs/architecture/previews/{name}.svg"
        pieces.extend(
            [
                "",
                "<details>",
                f"<summary>{title} · <a href=\"{mmd}\">Mermaid source</a></summary>",
                "",
                f"<img src=\"{svg}\" alt=\"{title} generated from repository source\" width=\"100%\" />",
                "",
                "</details>",
            ]
        )
    pieces.extend(
        [
            "",
            "Regenerate locally with `npm ci`, `npx puppeteer browsers install chrome`, "
            "and `npm run architecture:generate`. The source and dependency analysis "
            "uses Python AST and Babel; unsupported or dynamic relationships are "
            "omitted or explicitly marked as inferred.",
        ]
    )
    return "\n".join(pieces)


def _contributor_cards(contributor_data: dict[str, Any]) -> str:
    cards = []
    for item in contributor_data["contributors"][:18]:
        name = item["name"]
        href = item.get("profile_url")
        avatar = item["avatar"]
        image = (
            f'<img src="{html.escape(avatar, quote=True)}" width="72" height="72" '
            f'alt="{html.escape(name, quote=True)} avatar" />'
        )
        if href:
            if not re.fullmatch(r"https://github\.com/[A-Za-z0-9-]+", href):
                href = None
        if href:
            image = f'<a href="{html.escape(href, quote=True)}">{image}</a>'
        cards.append(
            f'<td align="center">{image}<br /><sub>{html.escape(name)}<br />'
            f"{html.escape(str(item['contributions']))} contributions</sub></td>"
        )
    if not cards:
        return "No commit authors were available in this checkout yet."
    rows = [
        "<table>",
        "<tr>" + "".join(cards[:6]) + "</tr>",
    ]
    for offset in range(6, len(cards), 6):
        rows.extend(["<tr>" + "".join(cards[offset : offset + 6]) + "</tr>"])
    rows.append("</table>")
    return "\n".join(rows)


def _render_readme(
    root: Path,
    repo: str,
    stack: list[str],
    contributor_data: dict[str, Any],
) -> None:
    owner, repository = repo.split("/", 1)
    stack_block = "\n".join(f"- **{item}**" for item in stack)
    if not stack_block:
        stack_block = "- No technology stack entries were detected from source/manifests."
    template = (
        root / "scripts" / "architecture" / "templates" / "README.md.in"
    ).read_text(encoding="utf-8")
    values = {
        "{{REPOSITORY}}": repo,
        "{{REPOSITORY_URL}}": f"https://github.com/{repo}",
        "{{OWNER}}": owner,
        "{{ARCHITECTURE_DIAGRAMS}}": _architecture_readme_section(),
        "{{TECH_STACK}}": stack_block,
        "{{CONTRIBUTOR_CARDS}}": _contributor_cards(contributor_data),
    }
    for marker, value in values.items():
        template = template.replace(marker, value)
    if re.search(r"\{\{[A-Z_]+\}\}", template):
        raise ValueError("README template contains an unrendered placeholder.")
    (root / "README.md").write_text(template, encoding="utf-8")


def _renderer(root: Path) -> list[str]:
    local = root / "node_modules" / ".bin" / (
        "mmdc.cmd" if os.name == "nt" else "mmdc"
    )
    executable = str(local) if local.is_file() else shutil.which("mmdc")
    if not executable:
        raise RuntimeError(
            "Mermaid CLI was not found. Run `npm ci`, then install its browser with "
            "`npx puppeteer browsers install chrome`."
        )
    return [executable]


def render_diagrams(root: Path, diagrams: dict[str, str], output_dir: Path) -> None:
    command = _renderer(root)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, source in diagrams.items():
        mmd_path = root / "docs" / "architecture" / f"{name}.mmd"
        mmd_path.parent.mkdir(parents=True, exist_ok=True)
        mmd_path.write_text(source, encoding="utf-8")
        svg_path = output_dir / f"{name}.svg"
        result = subprocess.run(
            [
                *command,
                "-i",
                str(mmd_path),
                "-o",
                str(svg_path),
                "-t",
                "neutral",
                "-b",
                "transparent",
            ],
            cwd=root,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(
                f"Mermaid rendering failed for {mmd_path.relative_to(root)}:\n"
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        if not svg_path.is_file() or svg_path.stat().st_size == 0:
            raise RuntimeError(f"Mermaid CLI produced no SVG for {mmd_path}.")


def analyze_repository(root: Path) -> dict[str, Any]:
    index = SourceIndex.build(root)
    dependencies_data = dependencies.analyze(root, index)
    module_data = modules.analyze(index)
    function_data = functions.analyze(index)
    class_data = classes.analyze(index)
    route_data = routes.analyze(index)
    runtime_data = runtime.analyze(index)
    compiler_data = compiler.analyze(index, function_data)
    permission_data = permissions.analyze(index, runtime_data)
    storage_data = storage.analyze(index, runtime_data)
    build_data = build.analyze(root)

    runtime_diagram, agent_diagram = _runtime_diagrams(
        runtime_data,
        permission_data,
    )
    diagrams = {
        "project-structure": _project_structure(index, module_data),
        "dependencies": dependencies_data["diagram"],
        "modules": module_data["diagram"],
        "call-graph": function_data["diagram"],
        "class-relationships": class_data["diagram"],
        "lexer-parser": compiler_data["diagram"],
        "api-architecture": route_data["diagram"],
        "llm-runtime": runtime_diagram,
        "agent-execution": agent_diagram,
        "permissions": permission_data["diagram"],
        "storage": storage_data["diagram"],
        "build-pipelines": build_data["diagram"],
    }
    return {
        "index": index,
        "dependencies": dependencies_data,
        "modules": module_data,
        "functions": function_data,
        "classes": class_data,
        "routes": route_data,
        "runtime": runtime_data,
        "compiler": compiler_data,
        "permissions": permission_data,
        "storage": storage_data,
        "build": build_data,
        "diagrams": diagrams,
    }


def generate(root: Path, *, offline: bool = False) -> None:
    root = root.resolve()
    result = analyze_repository(root)
    architecture_dir = root / "docs" / "architecture"
    previews_dir = architecture_dir / "previews"
    assets_dir = architecture_dir / "assets"
    architecture_dir.mkdir(parents=True, exist_ok=True)
    previews_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    source_count = len(result["modules"]["modules"])
    route_count = len(result["routes"]["routes"])
    repo = contributors.repository_name(root)
    token = None if offline else (os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN"))
    contributor_data, stats = contributors.generate(
        root,
        assets_dir,
        token=token,
        repo=repo,
        offline=offline,
        source_files=source_count,
        api_routes=route_count,
    )

    manifest = {
        "repository": repo,
        "analysis": {
            "source_files": source_count,
            "python_modules": sum(
                item["language"] == "Python" for item in result["modules"]["modules"]
            ),
            "javascript_modules": sum(
                item["language"] == "JavaScript/TypeScript"
                for item in result["modules"]["modules"]
            ),
            "functions": len(result["functions"]["functions"]),
            "classes": len(result["classes"]["classes"]),
            "api_routes": result["routes"]["routes"],
            "module_groups": result["modules"]["groups"],
            "module_import_edges": result["modules"]["edges"],
            "dependencies": result["dependencies"]["manifests"],
            "runtime_components": result["runtime"]["components"],
            "runtime_constructor_edges": result["runtime"]["constructor_edges"],
            "runtime_adapter_edges": result["runtime"]["adapter_edges"],
            "compiler_components": result["compiler"]["components"],
            "storage": {
                "database": result["storage"]["database"],
                "tables": result["storage"]["tables"],
            },
            "build": {
                "package_scripts": result["build"]["package_scripts"],
                "workflows": result["build"]["workflows"],
            },
        },
        "interpretation": {
            "python": "Python AST facts",
            "javascript": "Babel parser AST facts",
            "direct_calls": "Unique local calls only; dynamic dispatch omitted",
            "technology_roles": "Detected from imports, manifests, and file locations",
            "compiler_stage_labels": "Inferred from names and paths; no standalone lexer detected",
        },
    }
    (architecture_dir / "architecture.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    render_diagrams(root, result["diagrams"], previews_dir)
    _render_readme(root, repo, result["dependencies"]["stack"], contributor_data)
    validate_generated(root, require_mermaid=False)
    print(
        f"Generated README, {len(result['diagrams'])} Mermaid/SVG diagrams, "
        f"and {len(contributor_data['contributors'])} local contributor avatars."
    )


def validate_only(root: Path) -> None:
    root = root.resolve()
    validate_generated(root, require_mermaid=True)
    print("Architecture JSON, Mermaid, SVG assets, and README links validated.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate source-derived project architecture docs.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--offline", action="store_true", help="Use local git contributors; do not query GitHub.")
    parser.add_argument("--validate-only", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        if arguments.validate_only:
            validate_only(arguments.root)
        else:
            generate(arguments.root, offline=arguments.offline)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Architecture generation failed: {error}", file=sys.stderr)
        return 1
    return 0
