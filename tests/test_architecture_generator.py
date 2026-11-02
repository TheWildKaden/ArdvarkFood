from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from infrastructure.architecture.analyzers.dependencies import _read_requirements
from infrastructure.architecture.generator import analyze_repository
from infrastructure.architecture.index import SourceIndex


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def analysis() -> dict:
    return analyze_repository(ROOT)


def test_source_index_detects_real_app_routes_and_runtime_wiring(analysis: dict) -> None:
    result = analysis

    route_pairs = {
        (route["method"], route["path"])
        for route in result["routes"]["routes"]
    }
    assert ("POST", "/api/chat") in route_pairs
    assert ("POST", "/api/runtime/chat") in route_pairs
    assert any(
        edge["from"].endswith(".AgentRuntime")
        and edge["to"] == "AgentLoop"
        for edge in result["runtime"]["constructor_edges"]
    )
    assert any(
        edge["from"].endswith("ToolExecutor.execute")
        and edge["to"] == "PermissionManager.authorize"
        for edge in result["runtime"]["execution_edges"]
    )


def test_parser_and_encoder_diagram_does_not_invent_a_lexer(analysis: dict) -> None:
    result = analysis

    names = {item["name"] for item in result["compiler"]["components"]}
    assert "parse_tagged_text" in names
    assert "encode_messages" in names
    assert "bpe" in names
    assert not any(name.lower() == "lexer" for name in names)
    assert "No standalone lexer or parser package was detected." in result["compiler"]["diagram"]


def test_project_structure_diagram_lists_moved_top_level_components_once(
    analysis: dict,
) -> None:
    diagram = analysis["diagrams"]["project-structure"]

    for component in ("agent", "cli", "core", "infrastructure", "packages", "runtime", "services", "website"):
        assert diagram.count(f'  {component}["') == 1
    assert '  Agent["' not in diagram
    assert '  Runtime["' not in diagram


def test_optional_cli_dependency_is_included_in_architecture_manifest(
    analysis: dict,
) -> None:
    manifests = analysis["dependencies"]["manifests"]

    assert manifests["cli/requirements.txt"] == ["textual"]


def test_source_index_uses_babel_for_javascript_and_python_ast_for_python() -> None:
    index = SourceIndex.build(ROOT)

    languages = {
        "Python" if path.suffix == ".py" else "JavaScript/TypeScript"
        for path in [*index.python_modules, *(Path(item["path"]) for item in index.javascript_modules)]
    }
    assert languages == {"Python", "JavaScript/TypeScript"}
    app = next(
        item for item in index.javascript_modules
        if item["path"].endswith("website/assets/app.js")
    )
    assert app["imports"] == []
    assert not any(
        item["path"].startswith("website/stock-watch/")
        for item in index.javascript_modules
    )


def test_utf16_requirements_manifest_is_parsed(tmp_path: Path) -> None:
    manifest = tmp_path / "requirements.txt"
    manifest.write_text("FastAPI>=0.1\nhttpx==0.2\n# skip\n", encoding="utf-16")

    assert _read_requirements(manifest) == ["FastAPI", "httpx"]


def test_analyzer_output_is_json_serializable(analysis: dict) -> None:
    result = analysis
    summary = {
        "routes": result["routes"]["routes"],
        "functions": result["functions"]["functions"],
        "classes": result["classes"]["classes"],
    }

    assert json.loads(json.dumps(summary))


def test_javascript_indexer_reports_parse_errors(tmp_path: Path) -> None:
    invalid = tmp_path / "bad.jsx"
    invalid.write_text("const = ;", encoding="utf-8")
    indexer = ROOT / "infrastructure" / "architecture" / "js_indexer.mjs"
    result = subprocess.run(
        ["node", str(indexer)],
        input=json.dumps([str(invalid)]),
        text=True,
        capture_output=True,
        cwd=ROOT,
        check=True,
    )

    assert json.loads(result.stdout)[0]["error"]


@pytest.mark.parametrize(
    "filename",
    ["app.py", "agent/agent.py", "core/encoding/encoding.py"],
)
def test_python_sources_are_indexed(filename: str) -> None:
    index = SourceIndex.build(ROOT)

    assert any(path.relative_to(ROOT).as_posix() == filename for path in index.python_modules)
